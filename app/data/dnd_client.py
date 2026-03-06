from __future__ import annotations

from typing import Any

import httpx

from app.data.cache import SQLiteCache


class DndApiClient:
    def __init__(
        self,
        cache: SQLiteCache,
        base_url: str = "https://www.dnd5eapi.co",
        timeout_seconds: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.cache = cache
        self.timeout_seconds = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
            )
        return self._client

    async def get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{normalized_path}"

        cached = self.cache.get(url, params)
        if cached is not None:
            return cached

        client = await self._get_client()
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        self.cache.set(url, params, payload)
        return payload

    async def get_by_url(self, url: str) -> dict[str, Any] | list[Any]:
        if not url.startswith("http://") and not url.startswith("https://"):
            return await self.get(url)

        cached = self.cache.get(url, None)
        if cached is not None:
            return cached

        client = await self._get_client()
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        self.cache.set(url, None, payload)
        return payload

    async def get_class(self, class_index: str) -> dict[str, Any]:
        payload = await self.get(f"/api/classes/{class_index}")
        if not isinstance(payload, dict):
            msg = "Эндпоинт класса вернул некорректный формат данных"
            raise TypeError(msg)
        return payload

    async def get_class_levels(self, class_index: str) -> list[dict[str, Any]]:
        payload = await self.get(f"/api/classes/{class_index}/levels")
        if not isinstance(payload, list):
            msg = "Эндпоинт уровней класса вернул некорректный формат данных"
            raise TypeError(msg)
        return [entry for entry in payload if isinstance(entry, dict)]

    async def get_classes(self) -> list[dict[str, str]]:
        payload = await self.get("/api/classes")
        if not isinstance(payload, dict):
            msg = "Эндпоинт списка классов вернул некорректный формат данных"
            raise TypeError(msg)

        results = payload.get("results", [])
        if not isinstance(results, list):
            msg = "Эндпоинт списка классов вернул некорректное поле results"
            raise TypeError(msg)

        classes: list[dict[str, str]] = []
        for entry in results:
            if not isinstance(entry, dict):
                continue
            index = entry.get("index")
            name = entry.get("name")
            if isinstance(index, str) and isinstance(name, str):
                classes.append({"index": index, "name": name})
        return classes

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
