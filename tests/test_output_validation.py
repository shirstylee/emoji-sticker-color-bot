from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

from app.models.source import MediaFormat
from app.recolor.color_math import parse_color
from app.recolor.tgs import TgsError, save_tgs
from app.recolor.webm import ffmpeg_executable, recolor_webm_file
from app.validators.output import OutputValidationError, validate_processed_output


def tgs_document(fps: int = 60) -> dict[str, object]:
    return {
        "v": "5.7.4",
        "fr": fps,
        "ip": 0,
        "op": fps,
        "w": 512,
        "h": 512,
        "layers": [],
    }


@pytest.mark.asyncio
async def test_static_custom_emoji_output_is_validated_by_content(tmp_path: Path) -> None:
    path = tmp_path / "emoji.webp"
    Image.new("RGBA", (100, 100), (20, 40, 60, 128)).save(path, "WEBP", lossless=True)

    await validate_processed_output(
        path,
        expected=MediaFormat.PNG,
        pack_custom=True,
        max_tgs_decompressed=1024 * 1024,
    )


@pytest.mark.asyncio
async def test_invalid_sticker_dimensions_are_rejected_before_upload(tmp_path: Path) -> None:
    path = tmp_path / "bad.webp"
    Image.new("RGBA", (100, 100), (20, 40, 60, 128)).save(path, "WEBP", lossless=True)

    with pytest.raises(OutputValidationError, match="512px"):
        await validate_processed_output(
            path,
            expected=MediaFormat.WEBP,
            pack_custom=False,
            max_tgs_decompressed=1024 * 1024,
        )


def test_tgs_with_non_telegram_fps_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(TgsError, match="timing"):
        save_tgs(tgs_document(30), tmp_path / "bad.tgs")


@pytest.mark.asyncio
async def test_generated_webm_has_vp9_no_audio_alpha_and_emoji_size(tmp_path: Path) -> None:
    ffmpeg = str(ffmpeg_executable())
    source = tmp_path / "source.webm"
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=64x32:d=0.2:r=10",
        "-an",
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
        "-y",
        str(source),
    )
    assert await process.wait() == 0
    output = tmp_path / "emoji.webm"
    await recolor_webm_file(
        source,
        output,
        parse_color("#2196F3"),
        side=100,
        cancel_event=asyncio.Event(),
        timeout=30,
    )

    await validate_processed_output(
        output,
        expected=MediaFormat.WEBM,
        pack_custom=True,
        max_tgs_decompressed=1024 * 1024,
    )
