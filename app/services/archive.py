"""ZIP input/output with traversal, symlink, count, size, and ratio protections."""

from __future__ import annotations

import shutil
import stat
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from app.constants import IGNORED_ARCHIVE_NAMES, SUPPORTED_EXTENSIONS
from app.validators.archive import UnsafeArchiveError
from app.validators.common import detect_format, sanitize_filename


def _validate_member(member: zipfile.ZipInfo, *, max_ratio: float) -> PurePosixPath:
    raw = member.filename.replace("\\", "/")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise UnsafeArchiveError("Archive contains an unsafe path")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise UnsafeArchiveError("Archive symlinks are not allowed")
    if member.file_size > 0:
        ratio = member.file_size / max(member.compress_size, 1)
        if ratio > max_ratio:
            raise UnsafeArchiveError("Archive compression ratio is unsafe")
    return path


def extract_zip(
    archive_path: Path,
    destination: Path,
    *,
    max_files: int = 200,
    max_total_size: int = 128 * 1024 * 1024,
    max_ratio: float = 100.0,
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    total = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) > max_files:
                raise UnsafeArchiveError("Archive contains too many files")
            for member in members:
                relative = _validate_member(member, max_ratio=max_ratio)
                if any(part.lower() in IGNORED_ARCHIVE_NAMES for part in relative.parts):
                    continue
                if relative.suffix.lower() == ".zip":
                    raise UnsafeArchiveError("Nested archives are not allowed")
                if relative.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                total += member.file_size
                if total > max_total_size:
                    raise UnsafeArchiveError("Archive extracted size exceeds the limit")
                output = destination / f"{len(extracted) + 1:03d}_{sanitize_filename(relative.name)}"
                with archive.open(member) as source, output.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                try:
                    detect_format(output)
                except ValueError:
                    output.unlink(missing_ok=True)
                    continue
                extracted.append(output)
    except (zipfile.BadZipFile, OSError) as error:
        raise UnsafeArchiveError("Invalid ZIP archive") from error
    if not extracted:
        raise UnsafeArchiveError("Archive contains no supported files")
    return extracted


def create_output_zip(
    files: Iterable[Path],
    destination: Path,
    *,
    pack_name: str,
    selected_color: str,
    mode: str,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    root = sanitize_filename(pack_name, "Recolored")
    ordered = list(files)
    counters: dict[str, int] = {}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for index, source in enumerate(ordered, 1):
            extension = source.suffix.lower().lstrip(".")
            counters[extension] = counters.get(extension, 0) + 1
            name = f"{index:03d}.{extension}"
            archive.write(source, f"{root}/{extension}/{name}")
        info = (
            f"Source pack title: {root}\nSelected color: {selected_color}\n"
            f"Processing mode: {mode}\nFile count: {len(ordered)}\n"
            f"Generated timestamp: {datetime.now(UTC).isoformat()}\n"
        )
        archive.writestr(f"{root}/info.txt", info)
    return destination


def split_output_zip(
    files: list[Path],
    output_dir: Path,
    *,
    pack_name: str,
    selected_color: str,
    mode: str,
    part_limit: int,
) -> list[Path]:
    """Create independent valid ZIP parts using a conservative uncompressed-size estimate."""

    groups: list[list[Path]] = []
    current: list[Path] = []
    current_size = 0
    for path in files:
        size = path.stat().st_size
        if current and current_size + size > int(part_limit * 0.92):
            groups.append(current)
            current, current_size = [], 0
        current.append(path)
        current_size += size
    if current:
        groups.append(current)
    results: list[Path] = []
    for index, group in enumerate(groups, 1):
        destination = output_dir / f"{sanitize_filename(pack_name)}_part{index:02d}.zip"
        create_output_zip(
            group,
            destination,
            pack_name=pack_name,
            selected_color=selected_color,
            mode=mode,
        )
        if destination.stat().st_size > part_limit:
            raise UnsafeArchiveError("A ZIP part still exceeds the upload boundary")
        results.append(destination)
    return results
