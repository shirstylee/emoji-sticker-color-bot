"""TGS validation facade."""

from __future__ import annotations

from pathlib import Path

from app.recolor.tgs import load_tgs, normalize_tgs_timing


def validate_tgs(path: Path, max_decompressed: int) -> None:
    document = load_tgs(
        path,
        max_decompressed=max_decompressed,
        strict_timing=False,
    )
    normalize_tgs_timing(document)
