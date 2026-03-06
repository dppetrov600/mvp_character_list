from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

RoleLiteral = Literal["damage", "tank", "control", "support", "skills"]
LLMBackendLiteral = Literal["ollama", "openai", "openai-compatible"]


class LLMRequestConfig(BaseModel):
    enabled: bool | None = None
    backend: LLMBackendLiteral | None = None
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)

    @field_validator("backend")
    @classmethod
    def _normalize_backend(cls, value: str | None) -> str | None:
        if value == "openai-compatible":
            return "openai"
        return value


class CharacterSpec(BaseModel):
    level: int = Field(ge=1, le=20)
    class_index: str
    role: RoleLiteral | None = None
    description: str | None = None
    generation_method: Literal["point_buy"] = "point_buy"
    srd_only: bool = True
    seed: int | None = None
    use_llm: bool | None = None
    llm_config: LLMRequestConfig | None = None
    selected_equipment_choices: list[str] | None = None


class EquipmentItem(BaseModel):
    index: str
    name: str
    quantity: int = 1
    url: str | None = None


class EquipmentBlock(BaseModel):
    items: list[EquipmentItem] = Field(default_factory=list)
    choices_explained: list[str] = Field(default_factory=list)


class ProficiencyBlock(BaseModel):
    skills: list[str] = Field(default_factory=list)


class DerivedStats(BaseModel):
    prof_bonus: int
    hp: int
    hp_explanation: str
    ac: int
    ac_explanation: str


class AsiHistoryEntry(BaseModel):
    level: int
    applied: dict[str, int]
    reason: str


class CharacterSheet(BaseModel):
    class_index: str
    level: int
    ability_scores: dict[str, int]
    modifiers: dict[str, int]
    proficiencies: ProficiencyBlock
    equipment: EquipmentBlock
    derived: DerivedStats
    asi_history: list[AsiHistoryEntry] = Field(default_factory=list)
    backstory: str | None = None
    decisions: list[str] = Field(default_factory=list)
