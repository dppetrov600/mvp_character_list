from __future__ import annotations

import pytest

from app.core.models import CharacterSpec
from app.core.optimizer import CharacterGenerator
from app.data.cache import SQLiteCache
from app.llm.service import LLMService


class StubProvider:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    async def chat(self, messages: list[dict[str, str]]) -> str:
        self.calls += 1
        return self.response

    async def close(self) -> None:
        return None


class FakeDndClient:
    async def get_class(self, class_index: str) -> dict:
        return {
            "index": class_index,
            "hit_die": 8,
            "saving_throws": [{"index": "dex"}, {"index": "int"}],
            "spellcasting": None,
            "proficiency_choices": [
                {
                    "choose": 2,
                    "from": [
                        {
                            "index": "skill-stealth",
                            "name": "Skill: Stealth",
                            "url": "/api/proficiencies/stealth",
                        },
                        {
                            "index": "skill-perception",
                            "name": "Skill: Perception",
                            "url": "/api/proficiencies/perception",
                        },
                        {
                            "index": "skill-athletics",
                            "name": "Skill: Athletics",
                            "url": "/api/proficiencies/athletics",
                        },
                    ],
                }
            ],
            "starting_equipment": [
                {
                    "equipment": {
                        "index": "leather-armor",
                        "name": "Leather Armor",
                        "url": "/api/equipment/leather-armor",
                    },
                    "quantity": 1,
                }
            ],
            "starting_equipment_options": [],
        }

    async def get_class_levels(self, class_index: str) -> list[dict]:
        return [
            {"level": 1, "ability_score_bonuses": 0},
            {"level": 4, "ability_score_bonuses": 2},
        ]

    async def get_by_url(self, url: str) -> dict:
        if "leather-armor" in url:
            return {
                "index": "leather-armor",
                "name": "Leather Armor",
                "armor_category": "Light",
                "armor_class": {"base": 11, "dex_bonus": True, "max_bonus": None},
            }
        return {"index": "unknown"}


class FailingLLMService:
    enabled = True

    async def extract_preferences(self, description: str):
        return None

    async def generate_backstory(self, description: str, sheet_summary: str, tone_tags=None):
        return None


@pytest.mark.asyncio
async def test_llm_preference_parsing_and_cache(tmp_path):
    cache = SQLiteCache(tmp_path / "llm.sqlite3")
    provider = StubProvider(
        '{"role":"skills","priority_stats":["DEX","WIS"],"desired_skills":["Stealth"]}'
    )
    service = LLMService(
        enabled=True,
        backend="ollama",
        model="test-model",
        provider=provider,
        cache=cache,
    )

    prefs1 = await service.extract_preferences("stealth scout")
    prefs2 = await service.extract_preferences("stealth scout")

    assert prefs1 is not None
    assert prefs1.role == "skills"
    assert prefs1.priority_stats == ["DEX", "WIS"]
    assert prefs1.desired_skills == ["Stealth"]
    assert prefs2 is not None
    assert provider.calls == 1

    await service.close()
    cache.close()


@pytest.mark.asyncio
async def test_llm_failure_fallback_returns_valid_sheet():
    generator = CharacterGenerator(dnd_client=FakeDndClient(), llm_service=FailingLLMService())

    sheet = await generator.generate(
        CharacterSpec(
            level=4,
            class_index="rogue",
            description="stealthy infiltrator",
            generation_method="point_buy",
            use_llm=True,
            seed=7,
        )
    )

    assert sheet.class_index == "rogue"
    assert sheet.derived.hp > 0
    assert sheet.derived.ac >= 10
    assert sheet.asi_history
    assert any("применена эвристика" in decision for decision in sheet.decisions)
