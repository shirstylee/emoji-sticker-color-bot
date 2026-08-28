"""TGS validation facade."""

from __future__ import annotations

from pathlib import Path

from app.recolor.tgs import load_tgs


def validate_tgs(path: Path, max_decompressed: int) -> None:
    load_tgs(path, max_decompressed=max_decompressed)

