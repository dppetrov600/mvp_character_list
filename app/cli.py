from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.models import CharacterSpec
from app.core.optimizer import CharacterGenerator
from app.data.cache import SQLiteCache
from app.data.dnd_client import DndApiClient
from app.llm.service import LLMService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SRD-only D&D 5e character")
    parser.add_argument("--level", type=int, required=True)
    parser.add_argument("--class-index", required=True)
    parser.add_argument("--role", choices=["damage", "tank", "control", "support", "skills"])
    parser.add_argument("--description")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--use-llm", action="store_true")
    return parser.parse_args()


async def _run() -> None:
    args = parse_args()
    spec = CharacterSpec(
        level=args.level,
        class_index=args.class_index,
        role=args.role,
        description=args.description,
        seed=args.seed,
        generation_method="point_buy",
        use_llm=args.use_llm,
    )

    cache = SQLiteCache(Path(".cache/dnd_api.sqlite3"))
    llm_cache = SQLiteCache(Path(".cache/llm_cache.sqlite3"))
    client = DndApiClient(cache=cache)
    llm_service = LLMService.from_env(cache=llm_cache)
    generator = CharacterGenerator(client, llm_service=llm_service)
    try:
        sheet = await generator.generate(spec)
    finally:
        await llm_service.close()
        await client.close()
        llm_cache.close()
        cache.close()

    print(json.dumps(sheet.model_dump(), indent=2, ensure_ascii=True))


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
