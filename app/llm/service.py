from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

from pydantic import ValidationError

from app.data.cache import SQLiteCache
from app.llm.models import PreferenceExtraction
from app.llm.providers import LLMProvider, OllamaProvider, OpenAICompatibleProvider


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    backend: str
    base_url: str
    model: str
    timeout_seconds: float


def llm_config_from_env() -> LLMConfig:
    enabled_raw = os.getenv("LLM_ENABLED", "0").strip().lower()
    enabled = enabled_raw in {"1", "true", "yes", "on"}
    backend = os.getenv("LLM_BACKEND", "ollama").strip().lower() or "ollama"
    default_base = "http://localhost:11434" if backend == "ollama" else "http://localhost:8001"
    base_url = os.getenv("LLM_BASE_URL", default_base).strip() or default_base
    model = os.getenv("LLM_MODEL", "").strip()
    timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "30").strip() or "30")
    return LLMConfig(
        enabled=enabled,
        backend=backend,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )


def _extract_json_fragment(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def heuristic_preferences(description: str) -> PreferenceExtraction:
    text = description.lower()

    role: str | None = None
    role_keywords = {
        "tank": {"tank", "frontline", "defender", "танк", "фронтлайн", "защитник"},
        "damage": {
            "damage",
            "dps",
            "striker",
            "assassin",
            "sniper",
            "archer",
            "урон",
            "дамаг",
            "снайпер",
            "убийца",
            "лучник",
        },
        "control": {"control", "crowd", "disable", "controller", "контроль", "контроллер"},
        "support": {"support", "healer", "buffer", "leader", "поддержка", "хил", "лекарь"},
        "skills": {"stealth", "scout", "thief", "trickster", "skills", "скрытность", "разведчик"},
    }
    for candidate_role, words in role_keywords.items():
        if any(word in text for word in words):
            role = candidate_role
            break

    priority_stats: list[str] = []
    stat_keywords = {
        "STR": {"strength", "melee", "brute", "сила", "ближний"},
        "DEX": {"dex", "stealth", "ranged", "agile", "finesse", "archer", "ловкость", "скрыт"},
        "CON": {"con", "durable", "surviv", "tank", "телосложение", "живуч"},
        "INT": {"int", "arcane", "scholar", "wizard", "интеллект", "аркан"},
        "WIS": {"wis", "insight", "perception", "druid", "cleric", "мудрость", "восприятие"},
        "CHA": {"cha", "social", "leader", "face", "bard", "warlock", "sorcer", "харизма"},
    }
    for stat, words in stat_keywords.items():
        if any(word in text for word in words):
            priority_stats.append(stat)
        if len(priority_stats) >= 3:
            break

    desired_skills: list[str] = []
    skill_aliases = {
        "Stealth": {"stealth", "sneak", "скрытность", "красться"},
        "Perception": {"perception", "aware", "scout", "восприятие"},
        "Athletics": {"athletics", "grapple", "climb", "атлетика"},
        "Arcana": {"arcana", "magic lore", "магия", "аркана"},
        "Investigation": {"investigation", "detective", "analyze", "расследование"},
        "Persuasion": {"persuasion", "diplomacy", "убеждение"},
        "Insight": {"insight", "read people", "проницательность"},
        "Survival": {"survival", "track", "выживание"},
    }
    for skill, words in skill_aliases.items():
        if any(word in text for word in words):
            desired_skills.append(skill)

    return PreferenceExtraction(
        role=role,
        priority_stats=priority_stats,
        desired_skills=desired_skills,
        tone_tags=[],
    )


class LLMService:
    def __init__(
        self,
        enabled: bool,
        backend: str,
        model: str,
        provider: LLMProvider | None,
        cache: SQLiteCache | None,
    ):
        self.enabled = enabled
        self.backend = backend
        self.model = model
        self.provider = provider
        self.cache = cache

    @classmethod
    def from_env(cls, cache: SQLiteCache | None = None) -> LLMService:
        config = llm_config_from_env()
        provider: LLMProvider | None = None

        if config.enabled and config.model:
            if config.backend == "ollama":
                provider = OllamaProvider(
                    base_url=config.base_url,
                    model=config.model,
                    timeout_seconds=config.timeout_seconds,
                )
            elif config.backend == "openai":
                provider = OpenAICompatibleProvider(
                    base_url=config.base_url,
                    model=config.model,
                    timeout_seconds=config.timeout_seconds,
                )

        return cls(
            enabled=config.enabled,
            backend=config.backend,
            model=config.model,
            provider=provider,
            cache=cache,
        )

    def _cache_lookup(self, task: str, prompt: str) -> str | None:
        if self.cache is None:
            return None
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        url = f"llm://{self.backend}/{self.model}/{task}"
        cached = self.cache.get(url, {"prompt_hash": prompt_hash})
        if isinstance(cached, dict) and isinstance(cached.get("text"), str):
            return cached["text"]
        return None

    def _cache_store(self, task: str, prompt: str, text: str) -> None:
        if self.cache is None:
            return
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        url = f"llm://{self.backend}/{self.model}/{task}"
        self.cache.set(url, {"prompt_hash": prompt_hash}, {"text": text})

    async def _chat_cached(self, task: str, messages: list[dict[str, str]]) -> str | None:
        if not self.enabled or self.provider is None:
            return None

        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        cached_text = self._cache_lookup(task, prompt)
        if cached_text is not None:
            return cached_text

        try:
            text = await self.provider.chat(messages)
        except Exception:  # noqa: BLE001
            return None

        self._cache_store(task, prompt, text)
        return text

    async def extract_preferences(self, description: str) -> PreferenceExtraction | None:
        if not description.strip():
            return PreferenceExtraction()

        messages = [
            {
                "role": "system",
                "content": (
                    "Извлеки предпочтения персонажа DnD только в виде строгого JSON. "
                    "Не добавляй markdown, комментарии или пояснения. "
                    "Схема: {role, priority_stats, desired_skills, tone_tags}. "
                    "role только из [damage,tank,control,support,skills]. "
                    "priority_stats: до 3 значений из [STR,DEX,CON,INT,WIS,CHA]. "
                    "desired_skills: названия навыков SRD."
                ),
            },
            {
                "role": "user",
                "content": description,
            },
        ]

        text = await self._chat_cached("preferences", messages)
        if text is None:
            return None

        fragment = _extract_json_fragment(text)
        if fragment is None:
            return None

        try:
            raw = json.loads(fragment)
            return PreferenceExtraction.model_validate(raw)
        except (json.JSONDecodeError, ValidationError):
            return None

    async def generate_backstory(
        self,
        description: str,
        sheet_summary: str,
        tone_tags: list[str] | None = None,
    ) -> str | None:
        messages = [
            {
                "role": "system",
                "content": (
                    "Напиши короткую фэнтези-предысторию на русском языке, обычным текстом. "
                    "Требования: 3-6 предложений, затем ровно 2 крючка (hooks) списком. "
                    'Каждая строка крючка начинается с "- ". '
                    "Используй только общие фэнтези формулировки и SRD-безопасные термины. "
                    "Не упоминай защищённые авторским правом названия сеттингов, персонажей, "
                    "мест или организаций. Английские слова не используй."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Описание: {description}\n"
                    f"Сводка персонажа: {sheet_summary}\n"
                    f"Тональность: {', '.join(tone_tags or [])}"
                ),
            },
        ]

        text = await self._chat_cached("backstory", messages)
        if text is None:
            return None

        cleaned = text.strip()
        return cleaned or None

    async def close(self) -> None:
        if self.provider is not None:
            await self.provider.close()
