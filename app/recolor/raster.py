"""Safe, alpha-preserving raster recoloring and Telegram dimension adaptation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.constants import TELEGRAM_CUSTOM_EMOJI_SIDE, TELEGRAM_REGULAR_STICKER_SIDE
from app.recolor.color_math import (
    ParsedColor,
    adaptive_alpha,
    recolor_rgb,
    recolor_texture_rgb,
)


class RasterError(ValueError):
    """Raster input or output is invalid or unsafe."""


def is_textured_image(rgb: np.ndarray, alpha: np.ndarray) -> bool:
    """Conservatively detect photo-like texture rather than flat sticker art."""

    source = np.asarray(rgb, dtype=np.uint8)
    opacity = np.asarray(alpha, dtype=np.uint8)
    if source.ndim != 3 or source.shape[-1] != 3 or opacity.shape != source.shape[:2]:
        return False
    height, width = opacity.shape
    step = max(1, int(np.ceil(np.sqrt((height * width) / 65_536))))
    sampled = source[::step, ::step]
    visible = opacity[::step, ::step] > 8
    if int(np.count_nonzero(visible)) < 256:
        return False

    quantized = sampled >> 4
    packed = (
        quantized[..., 0].astype(np.uint16) * 256
        + quantized[..., 1].astype(np.uint16) * 16
        + quantized[..., 2].astype(np.uint16)
    )
    counts = np.bincount(packed[visible], minlength=4096)
    populated = counts[counts > 0]
    if populated.size < 96:
        return False
    probabilities = populated.astype(np.float64) / float(populated.sum())
    entropy = float(-np.sum(probabilities * np.log2(probabilities)))
    if entropy < 3.6:
        return False

    normalized = sampled.astype(np.float64) / 255.0
    luminance = (
        normalized[..., 0] * 0.2126
        + normalized[..., 1] * 0.7152
        + normalized[..., 2] * 0.0722
    )
    horizontal = np.abs(np.diff(luminance, axis=1))
    horizontal_visible = visible[:, 1:] & visible[:, :-1]
    vertical = np.abs(np.diff(luminance, axis=0))
    vertical_visible = visible[1:, :] & visible[:-1, :]
    differences = np.concatenate(
        (horizontal[horizontal_visible], vertical[vertical_visible])
    )
    if differences.size == 0:
        return False
    fine_detail = np.mean((differences > 0.02) & (differences < 0.25))
    return bool(fine_detail >= 0.08)


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


def recolor_image(
    image: Image.Image,
    target: ParsedColor,
    *,
    adaptive: bool = False,
    strong: bool = False,
    texture_mode: bool | None = None,
    intensity: float = 1.0,
) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3].copy()
    output = np.empty_like(rgba)
    if adaptive:
        output[..., :3] = 255
        output[..., 3] = adaptive_alpha(rgba[..., :3], alpha)
    elif strong:
        output[..., :3] = recolor_rgb(
            rgba[..., :3],
            target,
            weights=alpha.astype(np.float64) / 255.0,
            chroma_scale=1.35,
            contrast_scale=0.62,
            strength=intensity,
        )
        output[..., 3] = alpha
    elif texture_mode is True or (
        texture_mode is None and is_textured_image(rgba[..., :3], alpha)
    ):
        output[..., :3] = recolor_texture_rgb(
            rgba[..., :3], target, strength=float(np.clip(0.72 * intensity, 0.0, 1.0))
        )
        output[..., 3] = alpha
    else:
        output[..., :3] = recolor_rgb(
            rgba[..., :3],
            target,
            weights=alpha.astype(np.float64) / 255.0,
            strength=intensity,
        )
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
    adaptive: bool = False,
    strong: bool = False,
    intensity: float = 1.0,
) -> Path:
    image = recolor_image(
        load_rgba(source, max_dimension=max_dimension, max_pixels=max_pixels),
        target,
        adaptive=adaptive,
        strong=strong,
        intensity=intensity,
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
