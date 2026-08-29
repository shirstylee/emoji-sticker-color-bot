from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.config import Settings
from app.constants import TELEGRAM_WEBM_MAX_BYTES
from app.models.job import RuntimeJob
from app.models.source import MediaFormat
from app.recolor.tgs import save_tgs
from app.recolor.tgs_webm import render_tgs_webm
from app.recolor.webm import probe_webm
from app.services.pipeline import ProcessingPipeline


def visible_tgs_document() -> dict[str, object]:
    return {
        "tgs": 1,
        "v": "5.7.4",
        "fr": 60,
        "ip": 0,
        "op": 30,
        "w": 512,
        "h": 512,
        "nm": "Render test",
        "ddd": 0,
        "assets": [],
        "layers": [
            {
                "ddd": 0,
                "ind": 1,
                "ty": 4,
                "nm": "Rectangle",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [256, 256, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]},
                },
                "ao": 0,
                "shapes": [
                    {
                        "ty": "gr",
                        "it": [
                            {
                                "ty": "rc",
                                "d": 1,
                                "s": {"a": 0, "k": [280, 180]},
                                "p": {"a": 0, "k": [0, 0]},
                                "r": {"a": 0, "k": 24},
                            },
                            {
                                "ty": "fl",
                                "c": {"a": 0, "k": [0.1, 0.5, 1.0, 1.0]},
                                "o": {"a": 0, "k": 100},
                                "r": 1,
                            },
                            {
                                "ty": "tr",
                                "p": {"a": 0, "k": [0, 0]},
                                "a": {"a": 0, "k": [0, 0]},
                                "s": {"a": 0, "k": [100, 100]},
                                "r": {"a": 0, "k": 0},
                                "o": {"a": 0, "k": 100},
                                "sk": {"a": 0, "k": 0},
                                "sa": {"a": 0, "k": 0},
                            },
                        ],
                        "nm": "Rectangle group",
                    }
                ],
                "ip": 0,
                "op": 30,
                "st": 0,
                "bm": 0,
            }
        ],
    }


@pytest.mark.asyncio
async def test_tgs_renders_to_native_video_sticker_asset(tmp_path: Path) -> None:
    source = save_tgs(visible_tgs_document(), tmp_path / "source.tgs")
    destination = tmp_path / "delivery.webm"

    await render_tgs_webm(
        source,
        destination,
        side=512,
        maximum_bytes=TELEGRAM_WEBM_MAX_BYTES,
        cancel_event=asyncio.Event(),
        timeout=30,
    )

    info = await probe_webm(destination)
    assert (info.width, info.height) == (512, 512)
    assert info.codec == "vp9"
    assert info.has_alpha
    assert not info.has_audio
    assert 0 < info.fps <= 30
    assert 0 < info.duration <= 3
    assert destination.stat().st_size <= TELEGRAM_WEBM_MAX_BYTES


@pytest.mark.asyncio
async def test_pipeline_keeps_tgs_for_pack_and_builds_webm_for_chat(tmp_path: Path) -> None:
    class ImmediateScheduler:
        async def submit(self, _kind: object, operation: object, **_: object) -> Path:
            return await operation()  # type: ignore[operator]

    source = save_tgs(visible_tgs_document(), tmp_path / "processed" / "001.tgs")
    job = RuntimeJob(
        job_id="render-test",
        user_id=1,
        chat_id=1,
        language="ru",
        root=tmp_path,
    )
    pipeline = ProcessingPipeline(Settings(), ImmediateScheduler())  # type: ignore[arg-type]

    delivery, media_format = await pipeline.prepare_chat_sticker(job, source, MediaFormat.TGS)

    assert media_format == MediaFormat.WEBM
    assert delivery.suffix == ".webm"
    assert delivery.is_file()
    assert source.is_file()
    assert source.suffix == ".tgs"
