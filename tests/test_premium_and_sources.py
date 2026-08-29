from __future__ import annotations

from pathlib import Path

import pytest

from app.services.premium_emoji import PremiumEmojiRegistry
from app.services.source_resolver import find_pack_link, parse_pack_link
from app.services.unicode_emoji import extract_single_emoji
from app.validators.common import sanitize_filename


def test_real_premium_registry_is_loaded_from_main_txt() -> None:
    registry = PremiumEmojiRegistry.load(Path("Main.txt"))
    assert registry.loaded_entries == 708
    assert registry.invalid_entries == 0
    assert registry.mappings_available >= 30
    for semantic in ("SUCCESS", "ERROR", "COLOR", "CANCEL", "PACK", "ADMIN", "ZIP"):
        emoji_id = registry.button_id(semantic)
        assert emoji_id is not None and emoji_id.isdecimal()
    assert registry.icon("COLOR").custom_emoji_id == "5769635757211784031"
    assert registry.icon("LOADING").custom_emoji_id == "5258281774198311547"
    assert registry.button_id("FLAG_RU") == "5449408995691341691"
    assert registry.button_id("FLAG_EN") == "5202021044105257611"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://t.me/addstickers/My_pack", ("addstickers", "My_pack")),
        ("t.me/addemoji/My_pack/", ("addemoji", "My_pack")),
        ("https://t.me/addemoji/My_pack?start=1", ("addemoji", "My_pack")),
    ],
)
def test_strict_pack_links(value: str, expected: tuple[str, str]) -> None:
    assert parse_pack_link(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example/addemoji/name",
        "https://t.me/addemoji/name/extra",
        "https://user@t.me/addemoji/name",
        "https://t.me/addemoji/../name",
        "https://t.me/other/name",
    ],
)
def test_arbitrary_urls_and_unsafe_pack_links_rejected(value: str) -> None:
    assert parse_pack_link(value) is None


def test_embedded_pack_link_does_not_truncate_unsafe_path() -> None:
    assert find_pack_link("https://t.me/addemoji/name/extra") is None
    assert find_pack_link(f"https://t.me/addemoji/{'a' * 65}") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "[https://t.me/addemoji/OutlineEmoji](https://t.me/addemoji/OutlineEmoji)",
            ("addemoji", "OutlineEmoji"),
        ),
        (
            "Пак: https://t.me/addemoji/GabeNews_CIS — обработай",
            ("addemoji", "GabeNews_CIS"),
        ),
    ],
)
def test_pack_link_is_found_inside_message_text(
    value: str, expected: tuple[str, str]
) -> None:
    assert find_pack_link(value) == expected


@pytest.mark.parametrize("value", ["🔥", "❤️", "👨‍💻", "🏳️‍🌈"])
def test_unicode_emoji_grapheme_sequences(value: str) -> None:
    assert extract_single_emoji(value) == value


@pytest.mark.parametrize("value", ["hello", "🔥🔥", "A🔥", ""])
def test_non_single_emoji_rejected(value: str) -> None:
    assert extract_single_emoji(value) is None


def test_filename_sanitization() -> None:
    assert sanitize_filename("../../my<>file.png") == "my_file.png"
