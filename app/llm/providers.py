from __future__ import annotations

from abc import ABC, abstractmethod

import httpx


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, timeout_seconds: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
        )

    async def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        response = await self._client.post(f"{self.base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        message = data.get("message", {}) if isinstance(data, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            msg = "Некорректный формат ответа Ollama"
            raise ValueError(msg)
        return content

    async def close(self) -> None:
        await self._client.aclose()


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, timeout_seconds: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
        )

    async def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        response = await self._client.post(f"{self.base_url}/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            msg = "Некорректный формат ответа OpenAI-compatible API"
            raise ValueError(msg)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            msg = "В ответе OpenAI-compatible API отсутствует поле choices"
            raise ValueError(msg)
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            msg = "В ответе OpenAI-compatible API отсутствует content"
            raise ValueError(msg)
        return content

    async def close(self) -> None:
        await self._client.aclose()
