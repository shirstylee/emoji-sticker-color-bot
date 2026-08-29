from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.models.job import OutputType, RuntimeJob
from app.models.source import MediaFormat, SourceItem
from app.recolor.tgs import save_tgs
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
        "assets": [],
        "layers": [],
    }


@pytest.mark.asyncio
async def test_pipeline_delivers_tgs_natively_without_lossy_renderer(tmp_path: Path) -> None:
    class ImmediateScheduler:
        async def submit(self, _kind: object, operation: object, **_: object) -> Path:
            return await operation()  # type: ignore[operator]

    source = save_tgs(visible_tgs_document(), tmp_path / "processed" / "001.tgs")
    job = RuntimeJob(
        job_id="native-tgs-test",
        user_id=1,
        chat_id=1,
        language="ru",
        root=tmp_path,
    )
    pipeline = ProcessingPipeline(Settings(), ImmediateScheduler())  # type: ignore[arg-type]

    delivery, media_format = await pipeline.prepare_chat_sticker(job, source, MediaFormat.TGS)

    assert delivery == source
    assert media_format == MediaFormat.TGS
    assert not (tmp_path / "delivery").exists()


@pytest.mark.asyncio
async def test_existing_adaptive_tgs_is_preserved_byte_for_byte(tmp_path: Path) -> None:
    class ImmediateScheduler:
        async def submit(self, _kind: object, operation: object, **_: object) -> Path:
            return await operation()  # type: ignore[operator]

    document = visible_tgs_document()
    source = save_tgs(document, tmp_path / "source" / "001.tgs")
    original = source.read_bytes()
    item = SourceItem(
        index=1,
        path=source,
        format=MediaFormat.TGS,
        needs_repainting=True,
    )
    job = RuntimeJob(
        job_id="adaptive-copy-test",
        user_id=1,
        chat_id=1,
        language="ru",
        root=tmp_path,
        adaptive=True,
        output_type=OutputType.EMOJI_PACK,
    )

    result = await ProcessingPipeline(
        Settings(), ImmediateScheduler()  # type: ignore[arg-type]
    ).process_item(job, item)

    assert result.read_bytes() == original
