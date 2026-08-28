"""Source metadata retained only for the lifetime of a runtime job."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class SourceKind(StrEnum):
    STICKER = "sticker"
    CUSTOM_EMOJI = "custom_emoji"
    PACK = "pack"
    FILE = "file"
    ZIP = "zip"
    UNICODE = "unicode"
    MEDIA_GROUP = "media_group"


class MediaFormat(StrEnum):
    TGS = "tgs"
    WEBM = "webm"
    WEBP = "webp"
    PNG = "png"


@dataclass(slots=True)
class SourceItem:
    index: int
    path: Path
    format: MediaFormat
    preview_path: Path | None = None
    emoji_list: tuple[str, ...] = ("🎨",)
    original_name: str | None = None
    custom_emoji_id: str | None = None
    needs_repainting: bool = False


@dataclass(slots=True)
class SourceDescriptor:
    kind: SourceKind
    items: list[SourceItem] = field(default_factory=list)
    title: str | None = None
    sticker_type: str | None = None
    thumbnail_index: int | None = None

    @property
    def format_counts(self) -> dict[MediaFormat, int]:
        result: dict[MediaFormat, int] = {}
        for item in self.items:
            result[item.format] = result.get(item.format, 0) + 1
        return result
