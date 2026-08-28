"""Recoverable lifecycle cleanup helpers."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


async def remove_job_directory(path: Path, expected_root: Path) -> None:
    resolved = path.resolve()
    root = expected_root.resolve()
    if resolved.parent != root:
        raise ValueError("Refusing to remove a directory outside TEMP_ROOT")
    await asyncio.to_thread(shutil.rmtree, resolved, True)

