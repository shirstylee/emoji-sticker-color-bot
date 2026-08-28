"""RAM-only localization helpers."""

from __future__ import annotations

from app.i18n.en import EN
from app.i18n.ru import RU

CATALOGS = {"ru": RU, "en": EN}


def language_for(language_code: str | None) -> str:
    return "ru" if (language_code or "").lower().startswith("ru") else "en"


def text(language: str, key: str, **values: object) -> str:
    catalog = CATALOGS.get(language, EN)
    template = catalog.get(key, EN.get(key, key))
    return template.format(**values)

