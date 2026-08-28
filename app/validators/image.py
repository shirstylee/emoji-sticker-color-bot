"""Raster validation facade."""

from __future__ import annotations

from pathlib import Path

from app.recolor.raster import load_rgba


def validate_image(path: Path, *, max_dimension: int, max_pixels: int) -> tuple[int, int]:
    image = load_rgba(path, max_dimension=max_dimension, max_pixels=max_pixels)
    return image.size

