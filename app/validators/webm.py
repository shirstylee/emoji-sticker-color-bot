"""WEBM validation."""

from __future__ import annotations

from pathlib import Path

from app.recolor.webm import WebmInfo, probe_webm


async def validate_webm(path: Path) -> WebmInfo:
    return await probe_webm(path)

