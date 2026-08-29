"""A job is intentionally an in-memory object and is never serialized."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from app.models.source import SourceDescriptor


class JobStatus(StrEnum):
    SOURCE_ANALYSIS = "source_analysis"
    AWAITING_COLOR = "awaiting_color"
    GENERATING_PREVIEW = "generating_preview"
    AWAITING_PREVIEW_DECISION = "awaiting_preview_decision"
    AWAITING_OUTPUT_TYPE = "awaiting_output_type"
    AWAITING_PACK_NAME = "awaiting_pack_name"
    AWAITING_SPLIT_CONFIRMATION = "awaiting_split_confirmation"
    AWAITING_RESULT_ACTION = "awaiting_result_action"
    PROCESSING = "processing"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OutputType(StrEnum):
    EMOJI_PACK = "emoji_pack"
    STICKER_PACK = "sticker_pack"
    FILE = "file"
    ZIP = "zip"


@dataclass(slots=True)
class RuntimeJob:
    job_id: str
    user_id: int
    chat_id: int
    language: str
    root: Path
    is_admin: bool = False
    source: SourceDescriptor | None = None
    selected_color: str | None = None
    adaptive: bool = False
    output_type: OutputType | None = None
    pack_title: str | None = None
    status: JobStatus = JobStatus.SOURCE_ANALYSIS
    progress: int = 0
    total: int = 0
    color_changes: int = 0
    control_message_id: int | None = None
    preview_message_id: int | None = None
    split_allowed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_interaction_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    processing_task: asyncio.Task[object] | None = None
    created_sets: list[str] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)
    statistics_recorded: bool = False

    @property
    def short_id(self) -> str:
        return self.job_id[:6].upper()

    @property
    def interactive(self) -> bool:
        return self.status in {
            JobStatus.AWAITING_COLOR,
            JobStatus.AWAITING_PREVIEW_DECISION,
            JobStatus.AWAITING_OUTPUT_TYPE,
            JobStatus.AWAITING_PACK_NAME,
            JobStatus.AWAITING_SPLIT_CONFIRMATION,
            JobStatus.AWAITING_RESULT_ACTION,
        }

    def touch(self) -> None:
        self.last_interaction_at = datetime.now(UTC)

    def request_cancel(self) -> None:
        self.cancel_event.set()
        self.status = JobStatus.CANCELLED
        if self.processing_task and not self.processing_task.done():
            self.processing_task.cancel()
