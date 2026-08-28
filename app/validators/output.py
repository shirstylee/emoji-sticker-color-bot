"""Validation of every processed file before it is sent back to Telegram."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.constants import (
    TELEGRAM_CUSTOM_EMOJI_SIDE,
    TELEGRAM_REGULAR_STICKER_SIDE,
    TELEGRAM_STATIC_STICKER_MAX_BYTES,
    TELEGRAM_TGS_MAX_BYTES,
    TELEGRAM_VIDEO_MAX_DURATION_SECONDS,
    TELEGRAM_VIDEO_MAX_FPS,
    TELEGRAM_WEBM_MAX_BYTES,
)
from app.models.source import MediaFormat
from app.recolor.tgs import load_tgs
from app.recolor.webm import probe_webm
from app.validators.common import detect_format


class OutputValidationError(ValueError):
    """A processed file does not satisfy its declared/Telegram format."""


def _validate_raster(path: Path, actual: MediaFormat, pack_custom: bool | None) -> None:
    try:
        with Image.open(path) as image:
            image.load()
            expected_pillow = "PNG" if actual == MediaFormat.PNG else "WEBP"
            if image.format != expected_pillow:
                raise OutputValidationError("Raster content does not match its format")
            width, height = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise OutputValidationError("Raster output is not decodable") from error
    if width <= 0 or height <= 0:
        raise OutputValidationError("Raster output has invalid dimensions")
    if pack_custom is True and (width, height) != (
        TELEGRAM_CUSTOM_EMOJI_SIDE,
        TELEGRAM_CUSTOM_EMOJI_SIDE,
    ):
        raise OutputValidationError("Custom Emoji raster must be exactly 100x100")
    if pack_custom is False and (
        max(width, height) != TELEGRAM_REGULAR_STICKER_SIDE
        or min(width, height) > TELEGRAM_REGULAR_STICKER_SIDE
    ):
        raise OutputValidationError("Sticker raster must have one 512px side")
    if pack_custom is not None and path.stat().st_size > TELEGRAM_STATIC_STICKER_MAX_BYTES:
        raise OutputValidationError("Static sticker exceeds Telegram's size limit")


def _validate_tgs(path: Path, max_decompressed: int) -> None:
    if path.stat().st_size > TELEGRAM_TGS_MAX_BYTES:
        raise OutputValidationError("TGS exceeds Telegram's size limit")
    document = load_tgs(path, max_decompressed=max_decompressed)
    if float(document["fr"]) != 60.0:
        raise OutputValidationError("Telegram TGS must run at 60 FPS")


async def _validate_webm(path: Path, pack_custom: bool | None) -> None:
    if path.stat().st_size > TELEGRAM_WEBM_MAX_BYTES:
        raise OutputValidationError("WEBM exceeds Telegram's size limit")
    info = await probe_webm(path)
    if info.codec != "vp9":
        raise OutputValidationError("WEBM output must use the VP9 codec")
    if info.has_audio:
        raise OutputValidationError("WEBM output must not contain audio")
    if not info.has_alpha:
        raise OutputValidationError("WEBM output is missing its alpha channel")
    if info.duration > TELEGRAM_VIDEO_MAX_DURATION_SECONDS + 0.01:
        raise OutputValidationError("WEBM output exceeds 3 seconds")
    if info.fps <= 0 or info.fps > TELEGRAM_VIDEO_MAX_FPS + 0.01:
        raise OutputValidationError("WEBM output exceeds 30 FPS")
    if pack_custom is True and (info.width, info.height) != (
        TELEGRAM_CUSTOM_EMOJI_SIDE,
        TELEGRAM_CUSTOM_EMOJI_SIDE,
    ):
        raise OutputValidationError("Custom Emoji WEBM must be exactly 100x100")
    if pack_custom is False and (
        max(info.width, info.height) != TELEGRAM_REGULAR_STICKER_SIDE
        or min(info.width, info.height) > TELEGRAM_REGULAR_STICKER_SIDE
    ):
        raise OutputValidationError("Sticker WEBM must have one 512px side")


async def validate_processed_output(
    path: Path,
    *,
    expected: MediaFormat,
    pack_custom: bool | None,
    max_tgs_decompressed: int,
) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise OutputValidationError("Processed output is empty")
    try:
        actual = detect_format(path)
    except (OSError, ValueError) as error:
        raise OutputValidationError("Processed output has an unsupported signature") from error
    raster_formats = {MediaFormat.PNG, MediaFormat.WEBP}
    if actual != expected and not ({actual, expected} <= raster_formats):
        raise OutputValidationError("Processed output format does not match its source")
    if actual in raster_formats:
        _validate_raster(path, actual, pack_custom)
    elif actual == MediaFormat.TGS:
        _validate_tgs(path, max_tgs_decompressed)
    elif actual == MediaFormat.WEBM:
        await _validate_webm(path, pack_custom)
