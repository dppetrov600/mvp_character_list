from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.core.equipment import build_equipment_reference_payload
from app.core.models import CharacterSheet, CharacterSpec
from app.core.optimizer import CharacterGenerator

router = APIRouter()
WEB_INDEX_PATH = Path(__file__).resolve().parent.parent / "web" / "index.html"


def _get_generator(request: Request) -> CharacterGenerator:
    generator = getattr(request.app.state, "character_generator", None)
    if generator is None:
        msg = "Генератор персонажей не настроен"
        raise RuntimeError(msg)
    return generator


def _get_dnd_client(request: Request) -> Any:
    direct_client = getattr(request.app.state, "dnd_client", None)
    if direct_client is not None:
        return direct_client
    generator = _get_generator(request)
    return generator.dnd_client


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    try:
        return HTMLResponse(content=WEB_INDEX_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HTTPException(status_code=500, detail="UI недоступен") from exc


@router.get("/reference/classes")
async def reference_classes(request: Request) -> list[dict[str, str]]:
    try:
        client = _get_dnd_client(request)
        return await client.get_classes()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Ошибка DND API: {exc.response.status_code}"
        ) from exc


@router.get("/reference/class/{class_index}/equipment-options")
async def reference_class_equipment_options(
    class_index: str, request: Request
) -> dict[str, Any]:
    try:
        client = _get_dnd_client(request)
        class_data = await client.get_class(class_index)
        return build_equipment_reference_payload(class_index=class_index, class_data=class_data)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Ошибка DND API: {exc.response.status_code}"
        ) from exc


@router.post("/generate", response_model=CharacterSheet)
async def generate(spec: CharacterSpec, request: Request) -> CharacterSheet:
    generator = _get_generator(request)
    try:
        return await generator.generate(spec)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Ошибка DND API: {exc.response.status_code}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
