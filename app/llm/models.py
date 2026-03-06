from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.models import RoleLiteral

AbilityLiteral = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]


class PreferenceExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: RoleLiteral | None = None
    priority_stats: list[AbilityLiteral] = Field(default_factory=list, min_length=0, max_length=3)
    desired_skills: list[str] = Field(default_factory=list, min_length=0, max_length=8)
    tone_tags: list[str] = Field(default_factory=list, min_length=0, max_length=6)

    @field_validator("priority_stats", mode="before")
    @classmethod
    def _normalize_priority_stats(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            if not isinstance(raw, str):
                continue
            stat = raw.upper().strip()
            if stat in {"STR", "DEX", "CON", "INT", "WIS", "CHA"} and stat not in seen:
                seen.add(stat)
                normalized.append(stat)
            if len(normalized) >= 3:
                break
        return normalized

    @field_validator("desired_skills", mode="before")
    @classmethod
    def _normalize_skills(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            if not isinstance(raw, str):
                continue
            skill = raw.strip()
            if not skill:
                continue
            key = skill.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(skill)
            if len(normalized) >= 8:
                break
        return normalized

    @field_validator("tone_tags", mode="before")
    @classmethod
    def _normalize_tone_tags(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        tags: list[str] = []
        for raw in value:
            if isinstance(raw, str) and raw.strip():
                tags.append(raw.strip())
            if len(tags) >= 6:
                break
        return tags
