from __future__ import annotations

import re
from typing import Any

ABILITY_ORDER = ("STR", "DEX", "CON", "INT", "WIS", "CHA")

SKILL_TO_ABILITY: dict[str, str] = {
    "Acrobatics": "DEX",
    "Animal Handling": "WIS",
    "Arcana": "INT",
    "Athletics": "STR",
    "Deception": "CHA",
    "History": "INT",
    "Insight": "WIS",
    "Intimidation": "CHA",
    "Investigation": "INT",
    "Medicine": "WIS",
    "Nature": "INT",
    "Perception": "WIS",
    "Performance": "CHA",
    "Persuasion": "CHA",
    "Religion": "INT",
    "Sleight of Hand": "DEX",
    "Stealth": "DEX",
    "Survival": "WIS",
}

ROLE_SKILL_BONUS: dict[str, dict[str, float]] = {
    "damage": {"Athletics": 1.0, "Acrobatics": 1.0, "Stealth": 1.0, "Perception": 0.6},
    "tank": {"Athletics": 1.2, "Perception": 0.8, "Insight": 0.4, "Survival": 0.8},
    "control": {"Arcana": 1.2, "History": 0.8, "Investigation": 1.0, "Insight": 0.8},
    "support": {"Medicine": 1.2, "Insight": 1.0, "Persuasion": 1.0, "Perception": 0.8},
    "skills": {
        "Stealth": 1.2,
        "Perception": 1.0,
        "Investigation": 0.8,
        "Sleight of Hand": 1.0,
        "Persuasion": 0.8,
    },
}


def normalize_skill_name(name: str) -> str:
    if name.startswith("Skill: "):
        return name.replace("Skill: ", "", 1).strip()
    return name.strip()


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    return 2 + (level - 1) // 4


def calculate_level_hp(level: int, hit_die: int, con_mod: int) -> int:
    level = max(1, level)
    lvl1 = max(1, hit_die + con_mod)
    if level == 1:
        return lvl1
    per_level = max(1, (hit_die // 2 + 1) + con_mod)
    return lvl1 + (level - 1) * per_level


def average_damage_from_dice(damage_dice: str | None) -> float:
    if not damage_dice:
        return 0.0
    match = re.fullmatch(r"\s*(\d+)d(\d+)(?:\s*([+-])\s*(\d+))?\s*", damage_dice)
    if not match:
        return 0.0
    count, die_size, sign, flat = match.groups()
    base = int(count) * (int(die_size) + 1) / 2
    if sign and flat:
        adjustment = int(flat)
        base = base + adjustment if sign == "+" else base - adjustment
    return base


def ac_from_armor(armor_block: dict[str, Any], dex_mod: int) -> int:
    base = int(armor_block.get("base", 10))
    if not armor_block.get("dex_bonus", True):
        return base
    max_bonus = armor_block.get("max_bonus")
    if isinstance(max_bonus, int):
        return base + min(dex_mod, max_bonus)
    return base + dex_mod


def estimate_ac_from_items(item_details: list[dict[str, Any]], dex_mod: int) -> tuple[int, str]:
    baseline = 10 + dex_mod
    best_body: int | None = None
    shield_bonus = 0
    explanation_bits: list[str] = []
    fallback_used = False

    for detail in item_details:
        armor_block = detail.get("armor_class")
        if not isinstance(armor_block, dict):
            continue

        armor_category = str(detail.get("armor_category", "")).lower()
        name = detail.get("name", detail.get("index", "armor"))

        if "shield" in armor_category:
            raw_bonus = armor_block.get("bonus", armor_block.get("base", 0))
            if isinstance(raw_bonus, int):
                shield_bonus = max(shield_bonus, raw_bonus)
                explanation_bits.append(f"Щит {name} +{raw_bonus}")
            else:
                fallback_used = True
            continue

        raw_base = armor_block.get("base")
        if not isinstance(raw_base, int):
            fallback_used = True
            continue
        ac_value = ac_from_armor(armor_block, dex_mod)
        if best_body is None or ac_value > best_body:
            best_body = ac_value
            explanation_bits.append(f"Броня {name} -> {ac_value}")

    if best_body is None and shield_bonus == 0:
        return baseline, f"Броня/щит не найдены. КД = 10 + мод DEX ({dex_mod})"

    if best_body is None:
        total_ac = baseline + shield_bonus
        explanation_bits.insert(0, f"Броня не выбрана; базовое значение {baseline}")
    else:
        total_ac = best_body + shield_bonus

    if fallback_used:
        explanation_bits.append(
            "Некоторые данные по броне имели неожиданную структуру; применён частичный fallback"
        )

    return total_ac, "; ".join(explanation_bits)
