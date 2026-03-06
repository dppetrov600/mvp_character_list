from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.optimizer import CharacterGenerator


class StubDndClient:
    def __init__(self):
        self.calls = 0

    async def get_classes(self) -> list[dict[str, str]]:
        self.calls += 1
        return [
            {"index": "fighter", "name": "Fighter"},
            {"index": "rogue", "name": "Rogue"},
        ]

    async def get_class(self, class_index: str) -> dict:
        return {
            "index": class_index,
            "hit_die": 10,
            "saving_throws": [{"index": "str"}, {"index": "con"}],
            "spellcasting": None,
            "proficiency_choices": [],
            "starting_equipment": [
                {
                    "equipment": {
                        "index": "chain-mail",
                        "name": "Chain Mail",
                        "url": "/api/equipment/chain-mail",
                    },
                    "quantity": 1,
                }
            ],
            "starting_equipment_options": [
                {
                    "choose": 1,
                    "desc": "Выбор оружия",
                    "from": {
                        "option_set_type": "options_array",
                        "options": [
                            {
                                "option_type": "reference",
                                "item": {
                                    "index": "longsword",
                                    "name": "Longsword",
                                    "url": "/api/equipment/longsword",
                                },
                            },
                            {
                                "option_type": "reference",
                                "item": {
                                    "index": "battleaxe",
                                    "name": "Battleaxe",
                                    "url": "/api/equipment/battleaxe",
                                },
                            },
                        ],
                    },
                }
            ],
        }

    async def get_class_levels(self, class_index: str) -> list[dict]:
        return [{"level": 1, "ability_score_bonuses": 0}]

    async def get_by_url(self, url: str) -> dict:
        if "chain-mail" in url:
            return {
                "index": "chain-mail",
                "name": "Chain Mail",
                "armor_category": "Heavy",
                "armor_class": {"base": 16, "dex_bonus": False, "max_bonus": None},
            }
        return {"index": "generic-item", "name": "Generic Item"}


def build_test_app(
    dnd_client: StubDndClient | None = None,
    character_generator: CharacterGenerator | None = None,
) -> FastAPI:
    web_dir = Path(__file__).resolve().parent.parent / "app" / "web"
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=web_dir), name="static")
    if dnd_client is not None:
        app.state.dnd_client = dnd_client
    if character_generator is not None:
        app.state.character_generator = character_generator
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_root_serves_ui_index():
    app = build_test_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "Сгенерировать персонажа" in response.text


@pytest.mark.asyncio
async def test_reference_classes_returns_json_from_data_layer_mock():
    stub = StubDndClient()

    app = build_test_app(dnd_client=stub)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/reference/classes")

    assert response.status_code == 200
    assert response.json() == [
        {"index": "fighter", "name": "Fighter"},
        {"index": "rogue", "name": "Rogue"},
    ]
    assert stub.calls == 1


@pytest.mark.asyncio
async def test_reference_equipment_options_returns_ui_friendly_payload():
    stub = StubDndClient()
    app = build_test_app(dnd_client=stub)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/reference/class/fighter/equipment-options")

    assert response.status_code == 200
    data = response.json()
    assert data["class_index"] == "fighter"
    assert data["starting_equipment"]
    assert data["option_groups"]
    first_group = data["option_groups"][0]
    assert first_group["choose"] == 1
    assert first_group["options"][0]["option_id"].startswith("group-0-option-")


@pytest.mark.asyncio
async def test_generate_rejects_invalid_selected_equipment_choice_with_russian_error():
    stub = StubDndClient()
    generator = CharacterGenerator(dnd_client=stub, llm_service=None)
    app = build_test_app(dnd_client=stub, character_generator=generator)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/generate",
            json={
                "level": 1,
                "class_index": "fighter",
                "selected_equipment_choices": ["wrong-option-id"],
            },
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Недопустимый вариант снаряжения" in detail
