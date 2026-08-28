"""Safe, alpha-preserving raster recoloring and Telegram dimension adaptation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.constants import TELEGRAM_CUSTOM_EMOJI_SIDE, TELEGRAM_REGULAR_STICKER_SIDE
from app.recolor.color_math import ParsedColor, recolor_rgb


class RasterError(ValueError):
    """Raster input or output is invalid or unsafe."""


def load_rgba(
    path: Path, *, max_dimension: int = 4096, max_pixels: int = 16_000_000
) -> Image.Image:
    old_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with Image.open(path) as image:
            image.load()
            if image.width > max_dimension or image.height > max_dimension:
                raise RasterError("Raster dimensions exceed the configured limit")
            if image.width * image.height > max_pixels:
                raise RasterError("Raster pixel count exceeds the configured limit")
            return image.convert("RGBA")
    except (UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise RasterError("Invalid or unsafe raster image") from error
    finally:
        Image.MAX_IMAGE_PIXELS = old_limit


def recolor_image(image: Image.Image, target: ParsedColor) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3].copy()
    output = np.empty_like(rgba)
    output[..., :3] = recolor_rgb(rgba[..., :3], target, weights=alpha.astype(np.float64) / 255.0)
    output[..., 3] = alpha
    return Image.fromarray(output, mode="RGBA")


def fit_transparent(image: Image.Image, side: int) -> Image.Image:
    if image.width <= 0 or image.height <= 0:
        raise RasterError("Image has invalid dimensions")
    ratio = min(side / image.width, side / image.height)
    size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
    resized = image.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((side - size[0]) // 2, (side - size[1]) // 2))
    return canvas


def prepare_static_output(image: Image.Image, *, custom_emoji: bool) -> Image.Image:
    side = TELEGRAM_CUSTOM_EMOJI_SIDE if custom_emoji else TELEGRAM_REGULAR_STICKER_SIDE
    return fit_transparent(image, side)


def recolor_raster_file(
    source: Path,
    destination: Path,
    target: ParsedColor,
    *,
    custom_emoji: bool | None = None,
    max_dimension: int = 4096,
    max_pixels: int = 16_000_000,
    maximum_bytes: int | None = None,
) -> Path:
    image = recolor_image(
        load_rgba(source, max_dimension=max_dimension, max_pixels=max_pixels), target
    )
    if custom_emoji is not None:
        image = prepare_static_output(image, custom_emoji=custom_emoji)
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.lower()
    if suffix == ".webp":
        image.save(destination, format="WEBP", lossless=True, method=6)
        if maximum_bytes is not None and destination.stat().st_size > maximum_bytes:
            for quality in (95, 90, 85, 78):
                image.save(destination, format="WEBP", lossless=False, quality=quality, method=6)
                if destination.stat().st_size <= maximum_bytes:
                    break
            else:
                destination.unlink(missing_ok=True)
                raise RasterError("Static sticker exceeds Telegram's file-size limit")
    elif suffix == ".png":
        image.save(destination, format="PNG", optimize=True)
    else:
        raise RasterError("Output must be PNG or WEBP")
    return destination
