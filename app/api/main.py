from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.optimizer import CharacterGenerator
from app.data.cache import SQLiteCache
from app.data.dnd_client import DndApiClient
from app.llm.service import LLMService

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = SQLiteCache(Path(".cache/dnd_api.sqlite3"))
    llm_cache = SQLiteCache(Path(".cache/llm_cache.sqlite3"))
    client = DndApiClient(cache=cache)
    llm_service = LLMService.from_env(cache=llm_cache)
    app.state.dnd_client = client
    app.state.character_generator = CharacterGenerator(client, llm_service=llm_service)
    try:
        yield
    finally:
        await llm_service.close()
        await client.close()
        llm_cache.close()
        cache.close()


app = FastAPI(title="Генератор персонажа D&D 5e SRD", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.include_router(router)
