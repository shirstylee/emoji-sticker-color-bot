from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.config import Settings
from app.constants import TELEGRAM_VIDEO_SAFE_DURATION_SECONDS
from app.models.job import OutputType
from app.models.source import MediaFormat, SourceItem
from app.recolor.color_math import parse_color, srgb_to_oklab
from app.recolor.raster import (
    fit_transparent,
    is_textured_image,
    recolor_image,
    recolor_raster_file,
)
from app.recolor.webm import ffmpeg_executable, probe_webm, recolor_webm_file
from app.services.pipeline import ProcessingPipeline


@pytest.mark.asyncio
async def test_probe_webm_recovers_missing_container_timing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timingless.webm"
    source.write_bytes(b"\x1aE\xdf\xa3payload")
    header = (
        b"Duration: N/A\n"
        b"Stream #0:0: Video: vp9 (Profile 0), yuva420p, 100x100, 1k tbn\n"
        b"alpha_mode      : 1\n"
    )
    progress = b"frame=90\nout_time=00:00:03.000000\nprogress=end\n"
    calls = 0

    async def fake_run(_arguments: list[str], _timeout: float) -> tuple[int, bytes, bytes]:
        nonlocal calls
        calls += 1
        return (0, b"", header) if calls == 1 else (0, progress, b"")

    monkeypatch.setattr("app.recolor.webm._run_capture", fake_run)

    info = await probe_webm(source)

    assert info.duration == pytest.approx(3.0)
    assert info.fps == pytest.approx(30.0)
    assert info.width == 100 and info.height == 100
    assert info.has_alpha
    assert calls == 2


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


def test_adaptive_mask_preserves_symbol_as_negative_space() -> None:
    pixels = np.zeros((20, 20, 4), dtype=np.uint8)
    pixels[..., :3] = [255, 145, 20]
    pixels[..., 3] = 255
    pixels[5:15, 8:12, :3] = 255
    result = np.asarray(
        recolor_image(Image.fromarray(pixels, "RGBA"), parse_color("#000000"), adaptive=True)
    )
    assert 190 <= int(result[2, 2, 3]) <= 230
    assert int(result[10, 10, 3]) <= 20
    assert np.all(result[..., :3] == 255)


def test_adaptive_mask_keeps_dark_contours_denser_than_body() -> None:
    pixels = np.zeros((30, 30, 4), dtype=np.uint8)
    pixels[4:26, 4:26] = [35, 25, 20, 255]
    pixels[6:24, 6:24] = [240, 145, 25, 255]
    pixels[11:19, 13:17] = [255, 255, 255, 255]

    result = np.asarray(
        recolor_image(Image.fromarray(pixels, "RGBA"), parse_color("#000000"), adaptive=True)
    )

    contour = int(result[5, 15, 3])
    body = int(result[8, 15, 3])
    highlight = int(result[15, 15, 3])
    assert contour > body > highlight
    assert contour >= 245
    assert body >= 190


def test_existing_adaptive_emoji_gets_strong_tint_without_flattening() -> None:
    pixels = np.array(
        [[[245, 245, 245, 190], [120, 120, 120, 190], [30, 30, 30, 190]]],
        dtype=np.uint8,
    )
    result = np.asarray(
        recolor_image(Image.fromarray(pixels, "RGBA"), parse_color("#2196F3"), strong=True)
    )
    colors = result[0, :, :3]
    assert np.all(colors[:, 2] > colors[:, 0])
    assert len({tuple(color) for color in colors.tolist()}) == 3
    assert int(colors[0].sum()) > int(colors[1].sum()) > int(colors[2].sum())
    assert np.all(result[..., 3] == 190)


def test_texture_detector_keeps_flat_art_on_the_existing_recolor_path() -> None:
    flat = np.zeros((96, 96, 4), dtype=np.uint8)
    flat[..., 3] = 255
    flat[8:88, 8:88, :3] = [230, 80, 30]
    flat[24:72, 24:72, :3] = [30, 90, 220]

    rng = np.random.default_rng(42)
    y, x = np.mgrid[:96, :96]
    base = np.stack(
        (
            92 + x * 0.7 + y * 0.15,
            48 + x * 0.25 + y * 0.20,
            35 + x * 0.10 + y * 0.12,
        ),
        axis=-1,
    )
    textured_rgb = np.asarray(
        np.clip(base + rng.normal(0.0, 13.0, base.shape), 0, 255),
        dtype=np.uint8,
    )
    textured_alpha = np.full((96, 96), 255, dtype=np.uint8)

    assert not is_textured_image(flat[..., :3], flat[..., 3])
    assert is_textured_image(textured_rgb, textured_alpha)


def test_texture_recolor_preserves_lightness_black_white_and_alpha() -> None:
    pixels = np.array(
        [[[0, 0, 0, 77], [118, 72, 48, 180], [255, 255, 255, 255]]],
        dtype=np.uint8,
    )

    result = np.asarray(
        recolor_image(
            Image.fromarray(pixels, "RGBA"),
            parse_color("#FFEB3B"),
            texture_mode=True,
        )
    )
    source_l = srgb_to_oklab(pixels[..., :3].astype(np.float64) / 255.0)[0, :, 0]
    result_l = srgb_to_oklab(result[..., :3].astype(np.float64) / 255.0)[0, :, 0]

    np.testing.assert_array_equal(result[..., 3], pixels[..., 3])
    np.testing.assert_array_equal(result[0, 0, :3], pixels[0, 0, :3])
    np.testing.assert_array_equal(result[0, 2, :3], pixels[0, 2, :3])
    assert abs(float(result_l[1] - source_l[1])) < 0.006
    assert int(result[0, 1, 0]) > int(result[0, 1, 2])


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
async def test_adaptive_pipeline_ignores_opaque_telegram_thumbnail(
    tmp_path: Path,
) -> None:
    class ImmediateScheduler:
        async def submit(self, _kind: object, operation: object, **_: object) -> Path:
            return await operation()  # type: ignore[operator]

    source = tmp_path / "source" / "001.png"
    source.parent.mkdir(parents=True)
    pixels = np.zeros((40, 40, 4), dtype=np.uint8)
    pixels[5:35, 5:35] = [255, 145, 20, 255]
    pixels[12:28, 18:22] = [255, 255, 255, 255]
    Image.fromarray(pixels, "RGBA").save(source)
    thumbnail = source.with_name("001_preview.jpg")
    Image.new("RGB", (40, 40), (20, 20, 20)).save(thumbnail)
    item = SourceItem(
        index=1,
        path=source,
        format=MediaFormat.PNG,
        preview_path=thumbnail,
    )
    job = type(
        "AdaptiveJob",
        (),
        {
            "root": tmp_path,
            "selected_color": None,
            "output_type": OutputType.EMOJI_PACK,
            "is_admin": False,
            "adaptive": True,
        },
    )()

    result = await ProcessingPipeline(
        Settings(), ImmediateScheduler()  # type: ignore[arg-type]
    ).process_item(job, item, preview=True)  # type: ignore[arg-type]

    with Image.open(result) as preview:
        alpha = np.asarray(preview.convert("RGBA"))[..., 3]
        assert int(alpha[0, 0]) == 0
        assert int(alpha[50, 25]) > 190
        assert int(alpha[50, 50]) < 30


@pytest.mark.asyncio
async def test_pipeline_applies_strong_tint_to_existing_adaptive_source(
    tmp_path: Path,
) -> None:
    class ImmediateScheduler:
        async def submit(self, _kind: object, operation: object, **_: object) -> Path:
            return await operation()  # type: ignore[operator]

    source = tmp_path / "source" / "001.png"
    source.parent.mkdir(parents=True)
    pixels = np.full((100, 100, 4), (245, 245, 245, 210), dtype=np.uint8)
    pixels[25:75, 25:75, :3] = (80, 80, 80)
    Image.fromarray(pixels, "RGBA").save(source)
    item = SourceItem(
        index=1,
        path=source,
        format=MediaFormat.PNG,
        needs_repainting=True,
    )
    job = type(
        "StrongJob",
        (),
        {
            "root": tmp_path,
            "selected_color": "#FF0000",
            "output_type": OutputType.EMOJI_PACK,
            "is_admin": False,
            "adaptive": False,
        },
    )()

    result = await ProcessingPipeline(
        Settings(), ImmediateScheduler()  # type: ignore[arg-type]
    ).process_item(job, item)  # type: ignore[arg-type]

    with Image.open(result) as output:
        rgba = np.asarray(output.convert("RGBA"))
        visible = rgba[..., 3] > 0
        colored = rgba[..., :3][visible]
        assert np.all(colored[:, 0] > colored[:, 1])
        assert len({tuple(color) for color in colored.tolist()}) >= 2


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
        (
            "color=c=black@0.0:s=64x32:d=3.0:r=10,format=rgba,"
            "drawbox=x=16:y=8:w=32:h=16:color=red@1.0:t=fill:replace=1"
        ),
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
    assert output.duration <= TELEGRAM_VIDEO_SAFE_DURATION_SECONDS + 0.01
    assert destination.stat().st_size > 0

    decoded = tmp_path / "output.rgba"
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-v",
        "error",
        "-c:v",
        "libvpx-vp9",
        "-i",
        str(destination),
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-y",
        str(decoded),
    )
    assert await process.wait() == 0
    alpha = np.frombuffer(decoded.read_bytes(), dtype=np.uint8).reshape(
        output.height, output.width, 4
    )[..., 3]
    assert int(alpha[50, 10]) < 10
    assert int(alpha[50, 50]) > 240
