from __future__ import annotations

from pathlib import Path


def test_no_shell_true_or_persistent_users_table() -> None:
    code = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("app").rglob("*.py")
    ).lower()
    assert "shell=true" not in code.replace(" ", "")
    assert "create table if not exists users" not in code
    assert "create table users" not in code


def test_required_gitignore_entries() -> None:
    content = Path(".gitignore").read_text(encoding="utf-8")
    for entry in (
        ".venv/",
        ".env",
        "__pycache__/",
        "data/*.db",
        "temp/",
        "logs/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
    ):
        assert entry in content

