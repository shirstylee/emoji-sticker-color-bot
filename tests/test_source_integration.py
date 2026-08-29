from __future__ import annotations

import gzip
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.types import Chat, Document, Message, MessageEntity, Sticker, StickerSet, User
from PIL import Image

from app.config import Settings
from app.models.job import JobStatus
from app.models.source import MediaFormat, SourceKind
from app.services.jobs import JobManager
from app.services.source_resolver import resolve_message


def webp_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (32, 32), (255, 0, 0, 200)).save(output, "WEBP", lossless=True)
    return output.getvalue()


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (32, 32), (0, 255, 0, 200)).save(output, "PNG")
    return output.getvalue()


def tgs_bytes() -> bytes:
    document = {
        "v": "5.7.4",
        "fr": 30,
        "ip": 0,
        "op": 30,
        "w": 512,
        "h": 512,
        "layers": [],
    }
    return gzip.compress(json.dumps(document).encode())


def zip_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("one.png", png_bytes())
    return output.getvalue()


def sticker(file_id: str, *, custom: bool = False) -> Sticker:
    return Sticker(
        file_id=file_id,
        file_unique_id=f"unique-{file_id}",
        type="custom_emoji" if custom else "regular",
        width=32,
        height=32,
        is_animated=False,
        is_video=False,
        emoji="🎨",
        custom_emoji_id="custom-real-id" if custom else None,
        file_size=len(webp_bytes()),
    )


class FakeBot:
    def __init__(self) -> None:
        self.files = {
            "sticker": webp_bytes(),
            "custom": webp_bytes(),
            "pack-1": webp_bytes(),
            "pack-2": webp_bytes(),
            "png": png_bytes(),
            "tgs": tgs_bytes(),
            "zip": zip_bytes(),
        }

    async def get_file(self, file_id: str) -> Any:
        return SimpleNamespace(file_id=file_id, file_size=len(self.files[file_id]))

    async def download(self, remote: Any, destination: Path, **_: Any) -> None:
        destination.write_bytes(self.files[remote.file_id])

    async def get_sticker_set(self, _: str) -> StickerSet:
        return StickerSet(
            name="source_pack",
            title="Source Pack",
            sticker_type="regular",
            stickers=[sticker("pack-1"), sticker("pack-2")],
        )

    async def get_custom_emoji_stickers(self, _: list[str]) -> list[Sticker]:
        return [sticker("custom", custom=True)]


def message(**values: Any) -> Message:
    defaults: dict[str, Any] = {
        "message_id": 1,
        "date": 0,
        "chat": Chat(id=1, type="private"),
        "from_user": User(id=1, is_bot=False, first_name="Test"),
    }
    defaults.update(values)
    return Message(**defaults)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(temp_root=tmp_path / "jobs", max_input_download_mib=19)


async def new_job(settings: Settings) -> tuple[JobManager, Any]:
    manager = JobManager(settings.temp_root)
    await manager.startup_cleanup()
    job = await manager.create(user_id=1, chat_id=1, language="en", is_admin=False)
    return manager, job


@pytest.mark.asyncio
async def test_single_sticker_source(settings: Settings) -> None:
    manager, job = await new_job(settings)
    source = await resolve_message(FakeBot(), job, message(sticker=sticker("sticker")), settings)  # type: ignore[arg-type]
    assert source.kind == SourceKind.STICKER
    assert source.items[0].format == MediaFormat.WEBP
    await manager.finish(job.job_id)


@pytest.mark.asyncio
async def test_custom_emoji_entity_source(settings: Settings) -> None:
    manager, job = await new_job(settings)
    entity = MessageEntity(
        type="custom_emoji", offset=0, length=2, custom_emoji_id="custom-real-id"
    )
    source = await resolve_message(FakeBot(), job, message(text="🎨", entities=[entity]), settings)  # type: ignore[arg-type]
    assert source.kind == SourceKind.CUSTOM_EMOJI
    assert source.items[0].custom_emoji_id == "custom-real-id"
    await manager.finish(job.job_id)


@pytest.mark.asyncio
async def test_pack_link_source(settings: Settings) -> None:
    manager, job = await new_job(settings)
    source = await resolve_message(
        FakeBot(), job, message(text="https://t.me/addstickers/source_pack"), settings  # type: ignore[arg-type]
    )
    assert source.kind == SourceKind.PACK
    assert len(source.items) == 2
    await manager.finish(job.job_id)


@pytest.mark.asyncio
async def test_text_link_entity_pack_source(settings: Settings) -> None:
    manager, job = await new_job(settings)
    entity = MessageEntity(
        type="text_link",
        offset=0,
        length=3,
        url="https://t.me/addemoji/OutlineEmoji",
    )
    source = await resolve_message(
        FakeBot(),
        job,
        message(text="Пак", entities=[entity]),
        settings,  # type: ignore[arg-type]
    )
    assert source.kind == SourceKind.PACK
    assert len(source.items) == 2
    await manager.finish(job.job_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_id", "filename", "expected"),
    [("png", "image.png", MediaFormat.PNG), ("tgs", "animation.tgs", MediaFormat.TGS)],
)
async def test_png_and_tgs_document_sources(
    settings: Settings, file_id: str, filename: str, expected: MediaFormat
) -> None:
    manager, job = await new_job(settings)
    document = Document(
        file_id=file_id,
        file_unique_id=f"unique-{file_id}",
        file_name=filename,
        file_size=len(FakeBot().files[file_id]),
    )
    source = await resolve_message(FakeBot(), job, message(document=document), settings)  # type: ignore[arg-type]
    assert source.items[0].format == expected
    await manager.finish(job.job_id)


@pytest.mark.asyncio
async def test_zip_source(settings: Settings) -> None:
    manager, job = await new_job(settings)
    document = Document(
        file_id="zip",
        file_unique_id="unique-zip",
        file_name="files.zip",
        file_size=len(FakeBot().files["zip"]),
    )
    source = await resolve_message(FakeBot(), job, message(document=document), settings)  # type: ignore[arg-type]
    assert source.kind == SourceKind.ZIP
    assert source.items[0].format == MediaFormat.PNG
    await manager.finish(job.job_id)


@pytest.mark.asyncio
async def test_unicode_source_with_mock_local_renderer(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def render(_: str, destination: Path, __: Path | None) -> Path:
        destination.write_bytes(png_bytes())
        return destination

    monkeypatch.setattr("app.services.source_resolver.render_emoji", render)
    manager, job = await new_job(settings)
    source = await resolve_message(FakeBot(), job, message(text="👨‍💻"), settings)  # type: ignore[arg-type]
    assert source.kind == SourceKind.UNICODE
    assert source.items[0].format == MediaFormat.PNG
    await manager.finish(job.job_id, JobStatus.COMPLETED)
