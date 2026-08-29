"""Early validation for downloaded sources before a render job is accepted."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.constants import TELEGRAM_VIDEO_MAX_DURATION_SECONDS
from app.models.source import MediaFormat
from app.validators.common import detect_format
from app.validators.image import validate_image
from app.validators.tgs import validate_tgs
from app.validators.webm import validate_webm


class SourceValidationError(ValueError):
    """A source cannot be decoded safely or cannot become a Telegram sticker."""

    def __init__(self, message: str, *, message_key: str = "source_invalid") -> None:
        super().__init__(message)
        self.message_key = message_key


async def validate_source_file(
    path: Path,
    *,
    expected: MediaFormat | None = None,
    max_dimension: int,
    max_pixels: int,
    max_tgs_decompressed: int,
) -> MediaFormat:
    """Decode and inspect a source once, before the user chooses a color."""

    if not path.is_file() or path.stat().st_size <= 0:
        raise SourceValidationError("Source file is empty")
    try:
        actual = detect_format(path)
    except (OSError, ValueError) as error:
        raise SourceValidationError(
            "Source has an unsupported or invalid signature",
            message_key="unsupported",
        ) from error
    raster = {MediaFormat.PNG, MediaFormat.WEBP}
    if expected is not None and actual != expected and not ({actual, expected} <= raster):
        raise SourceValidationError(
            "Source content does not match its declared format",
            message_key="format_mismatch",
        )
    try:
        if actual in raster:
            await asyncio.to_thread(
                validate_image,
                path,
                max_dimension=max_dimension,
                max_pixels=max_pixels,
            )
        elif actual == MediaFormat.TGS:
            await asyncio.to_thread(validate_tgs, path, max_tgs_decompressed)
        elif actual == MediaFormat.WEBM:
            info = await validate_webm(path)
            if info.duration <= 0:
                raise SourceValidationError(
                    "WEBM duration is invalid", message_key="webm_invalid"
                )
            if info.duration > TELEGRAM_VIDEO_MAX_DURATION_SECONDS + 0.01:
                raise SourceValidationError(
                    "WEBM duration exceeds Telegram's 3-second limit",
                    message_key="video_too_long",
                )
            if (
                info.width > max_dimension
                or info.height > max_dimension
                or info.width * info.height > max_pixels
            ):
                raise SourceValidationError(
                    "WEBM dimensions exceed the configured safety limit",
                    message_key="webm_invalid",
                )
    except SourceValidationError:
        raise
    except (OSError, TypeError, ValueError) as error:
        message_key = {
            MediaFormat.PNG: "image_invalid",
            MediaFormat.WEBP: "image_invalid",
            MediaFormat.TGS: "tgs_invalid",
            MediaFormat.WEBM: "webm_invalid",
        }[actual]
        raise SourceValidationError(
            f"Source {actual.value.upper()} failed validation: {error}",
            message_key=message_key,
        ) from error
    return actual
