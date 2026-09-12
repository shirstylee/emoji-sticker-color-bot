from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from scripts import check_publication


def test_publication_audit_finds_deleted_secret_without_echoing_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    secret = "123456789:" + "A" * 35
    source = tmp_path / "settings.txt"
    source.write_text(secret, encoding="utf-8")
    git("add", "settings.txt")
    git("commit", "-m", "Initial fixture")
    source.write_text("removed", encoding="utf-8")
    git("add", "settings.txt")
    git("commit", "-m", "Remove fixture secret")
    monkeypatch.setattr(check_publication, "ROOT", tmp_path)

    assert check_publication.scan_worktree()[1] == []
    count, findings = check_publication.scan_history()
    assert count > 0
    assert any("Telegram bot token" in finding for finding in findings)
    assert all(secret not in finding for finding in findings)


def test_example_environment_can_be_loaded_before_credentials_are_configured() -> None:
    settings = Settings(_env_file=".env.example")  # type: ignore[call-arg]
    assert settings.owner_id == 0
    assert str(settings.source_code_url).startswith("https://")
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        settings.validate_runtime()


def test_deployment_urls_are_validated_and_settings_repr_hides_token() -> None:
    secret = "123456789:" + "A" * 35
    settings = Settings(bot_token=secret)
    assert secret not in repr(settings)
    with pytest.raises(ValidationError):
        Settings(source_code_url="javascript:alert(1)")
