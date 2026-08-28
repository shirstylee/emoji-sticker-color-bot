from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from app.services.archive import extract_zip
from app.validators.archive import UnsafeArchiveError

PNG = b"\x89PNG\r\n\x1a\n" + b"payload"


def make_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


@pytest.mark.parametrize("name", ["../escape.png", "/absolute.png", "safe/../../escape.png"])
def test_zip_traversal_rejected(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "input.zip"
    make_zip(archive, {name: PNG})
    with pytest.raises(UnsafeArchiveError, match="unsafe path"):
        extract_zip(archive, tmp_path / "out")


def test_zip_symlink_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo("link.png")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target.png")
    with pytest.raises(UnsafeArchiveError, match="symlink"):
        extract_zip(archive_path, tmp_path / "out")


def test_zip_bomb_like_ratio_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "ratio.zip"
    make_zip(archive, {"huge.png": PNG + b"A" * 200_000})
    with pytest.raises(UnsafeArchiveError, match="ratio"):
        extract_zip(archive, tmp_path / "out", max_ratio=10)


def test_zip_max_count_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "count.zip"
    make_zip(archive, {f"{index}.png": PNG for index in range(4)})
    with pytest.raises(UnsafeArchiveError, match="too many"):
        extract_zip(archive, tmp_path / "out", max_files=3)


def test_safe_zip_preserves_numeric_order_and_signatures(tmp_path: Path) -> None:
    archive = tmp_path / "safe.zip"
    make_zip(archive, {"nested/b.png": PNG, "a.png": PNG, ".DS_Store": b"ignored"})
    result = extract_zip(archive, tmp_path / "out")
    assert [path.name[:3] for path in result] == ["001", "002"]
    assert all(path.read_bytes().startswith(b"\x89PNG") for path in result)

