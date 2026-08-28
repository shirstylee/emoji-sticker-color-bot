from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.config import Settings
from app.models.job import OutputType
from app.models.source import MediaFormat, SourceItem
from app.recolor.color_math import parse_color
from app.recolor.raster import fit_transparent, recolor_raster_file
from app.recolor.webm import ffmpeg_executable, probe_webm, recolor_webm_file
from app.services.pipeline import ProcessingPipeline


def test_raster_output_dimensions_and_aspect_padding(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    destination = tmp_path / "sticker.webp"
    pixels = np.zeros((40, 80, 4), dtype=np.uint8)
    pixels[..., :3] = [255, 0, 0]
    pixels[..., 3] = 180
    Image.fromarray(pixels, "RGBA").save(source)
    recolor_raster_file(source, destination, parse_color("#03A9F4"), custom_emoji=False)
    with Image.open(destination) as result:
        assert result.size == (512, 512)
        alpha = np.asarray(result.convert("RGBA"))[..., 3]
        assert np.all(alpha[:100] == 0)
        assert int(alpha.max()) == 180


def test_fit_transparent_custom_emoji() -> None:
    image = Image.new("RGBA", (200, 100), (255, 255, 255, 255))
    result = fit_transparent(image, 100)
    assert result.size == (100, 100)
    assert result.getpixel((50, 0))[3] == 0
    assert result.getpixel((50, 50))[3] == 255


@pytest.mark.asyncio
async def test_tgs_preview_uses_static_thumbnail_instead_of_raw_unknown_file(
    tmp_path: Path,
) -> None:
    class ImmediateScheduler:
        async def submit(self, _kind: object, operation: object, **_: object) -> Path:
            return await operation()  # type: ignore[operator]

    thumbnail = tmp_path / "source" / "001_preview.jpg"
    thumbnail.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), (240, 160, 20)).save(thumbnail)
    item = SourceItem(
        index=1,
        path=tmp_path / "source" / "001.tgs",
        format=MediaFormat.TGS,
        preview_path=thumbnail,
    )
    job = type(
        "PreviewJob",
        (),
        {
            "root": tmp_path,
            "selected_color": "#2196F3",
            "output_type": OutputType.EMOJI_PACK,
            "is_admin": False,
        },
    )()
    pipeline = ProcessingPipeline(Settings(), ImmediateScheduler())  # type: ignore[arg-type]
    result = await pipeline.process_item(job, item, preview=True)  # type: ignore[arg-type]
    assert result.suffix == ".png"
    with Image.open(result) as preview:
        assert preview.format == "PNG"


@pytest.mark.asyncio
async def test_streaming_webm_pipeline(tmp_path: Path) -> None:
    ffmpeg = str(ffmpeg_executable())
    source = tmp_path / "source.webm"
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=64x32:d=0.25:r=10",
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
    info = await probe_webm(source)
    assert info.duration <= 3
    destination = tmp_path / "output.webm"
    await recolor_webm_file(
        source,
        destination,
        parse_color("#9C27B0"),
        side=100,
        cancel_event=asyncio.Event(),
        timeout=30,
    )
    output = await probe_webm(destination)
    assert output.width <= 100 and output.height <= 100
    assert output.fps <= 30
    assert destination.stat().st_size > 0
