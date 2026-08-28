"""Content-signature detection and safe names."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.source import MediaFormat

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
GZIP_SIGNATURE = b"\x1f\x8b"
RIFF_SIGNATURE = b"RIFF"
WEBM_EBML_SIGNATURE = b"\x1aE\xdf\xa3"
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def detect_format(path: Path) -> MediaFormat:
    with path.open("rb") as source:
        header = source.read(16)
    if header.startswith(PNG_SIGNATURE):
        return MediaFormat.PNG
    if header.startswith(GZIP_SIGNATURE):
        return MediaFormat.TGS
    if header.startswith(RIFF_SIGNATURE) and header[8:12] == b"WEBP":
        return MediaFormat.WEBP
    if header.startswith(WEBM_EBML_SIGNATURE):
        return MediaFormat.WEBM
    raise ValueError("Unsupported file signature")


def sanitize_filename(value: str, fallback: str = "file") -> str:
    name = Path(value.replace("\\", "/")).name.strip().strip(".")
    clean = SAFE_NAME_RE.sub("_", name).replace("__", "_")
    return clean[:100] or fallback

