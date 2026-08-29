"""Centralized rolling-window limits for regular users."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LimitsConfig:
    light_jobs_10_minutes: int = 30
    light_jobs_hour: int = 120
    light_jobs_day: int = 500
    jobs_10_minutes: int = 3
    jobs_hour: int = 12
    jobs_day: int = 40
    large_hour: int = 5
    large_day: int = 15
    huge_hour: int = 3
    huge_day: int = 8
    heavy_webm_hour: int = 3
    heavy_webm_day: int = 8
    preview_color_changes: int = 15
    active_regular_jobs: int = 1

    def as_settings(self) -> dict[str, int]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
            if field not in {"active_regular_jobs", "preview_color_changes"}
        }
