from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, User

from app.config import Settings
from app.handlers.workflow import _select_color
from app.models.job import JobStatus, RuntimeJob
from app.models.source import MediaFormat, SourceDescriptor, SourceItem, SourceKind
from app.services.pipeline import ProcessingPipeline
from app.services.premium_emoji import PremiumEmojiRegistry


def control_message() -> Message:
    return Message(
        message_id=50,
        date=0,
        chat=Chat(id=7, type="private"),
        from_user=User(id=999, is_bot=True, first_name="Bot"),
        text="Choose",
    )


@pytest.mark.asyncio
async def test_color_selection_builds_source_by_color_product_before_processing(
    tmp_path: Path,
) -> None:
    job = RuntimeJob(
        job_id="abcdef",
        user_id=7,
        chat_id=7,
        language="ru",
        root=tmp_path,
        source=SourceDescriptor(
            kind=SourceKind.CUSTOM_EMOJI,
            items=[
                SourceItem(1, tmp_path / "one.webp", MediaFormat.WEBP),
                SourceItem(2, tmp_path / "two.webp", MediaFormat.WEBP),
                SourceItem(3, tmp_path / "three.webp", MediaFormat.WEBP),
            ],
        ),
        status=JobStatus.AWAITING_COLOR,
    )
    registry = PremiumEmojiRegistry.load(Path("Main.txt"))
    context = SimpleNamespace(
        premium=registry,
        ui=SimpleNamespace(edit=AsyncMock(), answer=AsyncMock()),
        limits=SimpleNamespace(preview_color_changes=15),
        settings=SimpleNamespace(max_logical_items=200),
    )

    await _select_color(
        control_message(),
        job,
        "#FF0000 #0000FF",
        context,  # type: ignore[arg-type]
    )

    assert job.status == JobStatus.AWAITING_INTENSITY
    assert job.selected_colors == ["#FF0000", "#0000FF"]
    assert len(job.processing_items) == 6
    assert [item.target_color for item in job.processing_items] == [
        "#FF0000",
        "#FF0000",
        "#FF0000",
        "#0000FF",
        "#0000FF",
        "#0000FF",
    ]
    assert [item.source_index for item in job.processing_items] == [1, 2, 3, 1, 2, 3]
    rendered = context.ui.edit.await_args.args[1]
    assert "Будет результатов: <b>6</b>" in rendered
    callbacks = [
        row[0].callback_data
        for row in context.ui.edit.await_args.kwargs["reply_markup"].inline_keyboard
    ]
    assert callbacks[-1] == "job:abcdef:intensity_back"


@pytest.mark.asyncio
async def test_pipeline_retry_input_contains_failed_items_only(tmp_path: Path) -> None:
    items = [
        SourceItem(1, tmp_path / "one.webp", MediaFormat.WEBP, target_color="#FF0000"),
        SourceItem(2, tmp_path / "two.webp", MediaFormat.WEBP, target_color="#0000FF"),
    ]
    job = RuntimeJob(
        job_id="abcdef",
        user_id=7,
        chat_id=7,
        language="en",
        root=tmp_path,
        source=SourceDescriptor(kind=SourceKind.FILE, items=items),
        work_items=list(items),
        selected_color="#FF0000",
        selected_colors=["#FF0000", "#0000FF"],
    )
    pipeline = ProcessingPipeline(Settings(), SimpleNamespace())  # type: ignore[arg-type]

    async def fail_second(
        _: RuntimeJob, item: SourceItem, *, preview: bool = False
    ) -> Path:
        del preview
        if item.index == 2:
            raise ValueError("broken")
        return tmp_path / f"{item.index}.webp"

    pipeline.process_item = fail_second  # type: ignore[method-assign]
    first_outputs = await pipeline.process_all(job)

    assert [item.index for item, _ in first_outputs] == [1]
    assert [item.index for item in job.failed_items] == [2]

    job.work_items = list(job.failed_items)
    job.errors = []

    async def succeed(
        _: RuntimeJob, item: SourceItem, *, preview: bool = False
    ) -> Path:
        del preview
        return tmp_path / f"retry-{item.index}.webp"

    pipeline.process_item = succeed  # type: ignore[method-assign]
    retry_outputs = await pipeline.process_all(job)

    assert [item.index for item, _ in retry_outputs] == [2]
    assert job.failed_items == []
