from __future__ import annotations

import asyncio
import random
from typing import Any

from app.core.equipment import (
    EquipmentOptionChoice,
    build_equipment_choices,
    format_bundle_label,
)
from app.core.models import (
    AsiHistoryEntry,
    CharacterSheet,
    CharacterSpec,
    DerivedStats,
    EquipmentBlock,
    EquipmentItem,
    ProficiencyBlock,
    RoleLiteral,
)
from app.core.point_buy import point_buy_arrays, tuple_to_ability_scores
from app.core.rules import (
    ABILITY_ORDER,
    ROLE_SKILL_BONUS,
    SKILL_TO_ABILITY,
    ability_modifier,
    average_damage_from_dice,
    calculate_level_hp,
    estimate_ac_from_items,
    proficiency_bonus,
)
from app.data.dnd_client import DndApiClient
from app.data.mappers import (
    EquipmentBundle,
    EquipmentRef,
    extract_skill_names_from_choice,
)
from app.llm.models import PreferenceExtraction
from app.llm.providers import OllamaProvider, OpenAICompatibleProvider
from app.llm.service import LLMService, heuristic_preferences, llm_config_from_env

ROLE_ABILITY_BONUS: dict[str, dict[str, float]] = {
    "damage": {"STR": 1.5, "DEX": 1.5, "INT": 0.5, "CHA": 0.5},
    "tank": {"CON": 2.0, "STR": 1.1, "DEX": 0.7, "WIS": 0.3},
    "control": {"INT": 2.0, "WIS": 1.5, "CHA": 1.0, "DEX": 0.3},
    "support": {"WIS": 2.0, "CHA": 2.0, "CON": 0.8, "DEX": 0.3},
    "skills": {"DEX": 2.0, "WIS": 1.3, "INT": 1.0, "CHA": 1.0},
}

DESCRIPTION_ABILITY_HINTS: dict[str, str] = {
    "stealth": "DEX",
    "sneak": "DEX",
    "archer": "DEX",
    "ranged": "DEX",
    "скрыт": "DEX",
    "лучник": "DEX",
    "frontline": "STR",
    "melee": "STR",
    "ближн": "STR",
    "tank": "CON",
    "танк": "CON",
    "защит": "CON",
    "control": "INT",
    "контрол": "INT",
    "support": "WIS",
    "поддерж": "WIS",
    "social": "CHA",
    "социал": "CHA",
    "харизм": "CHA",
    "charisma": "CHA",
    "intelligence": "INT",
    "интеллект": "INT",
    "wisdom": "WIS",
    "мудрост": "WIS",
}


def _build_ability_weights(
    class_data: dict[str, Any],
    role: RoleLiteral | None,
    description: str | None,
    priority_stats: list[str] | None,
) -> dict[str, float]:
    weights = {ability: 1.0 for ability in ABILITY_ORDER}

    for save in class_data.get("saving_throws", []):
        if isinstance(save, dict):
            index = str(save.get("index", "")).upper()
            if index in weights:
                weights[index] += 2.0

    spellcasting = class_data.get("spellcasting")
    if isinstance(spellcasting, dict):
        spell_ability = spellcasting.get("spellcasting_ability")
        if isinstance(spell_ability, dict):
            index = str(spell_ability.get("index", "")).upper()
            if index in weights:
                weights[index] += 3.0

    if role and role in ROLE_ABILITY_BONUS:
        for ability, bonus in ROLE_ABILITY_BONUS[role].items():
            weights[ability] += bonus

    if priority_stats:
        for idx, stat in enumerate(priority_stats):
            upper = stat.upper()
            if upper in weights:
                weights[upper] += 3.0 - idx

    description_lower = (description or "").lower()
    for keyword, ability in DESCRIPTION_ABILITY_HINTS.items():
        if keyword in description_lower:
            weights[ability] += 0.8

    return weights


def _priority_order(
    ability_scores: dict[str, int],
    priority_stats: list[str] | None,
) -> list[str]:
    ordered: list[str] = []

    for stat in priority_stats or []:
        upper = stat.upper()
        if upper in ABILITY_ORDER and upper not in ordered:
            ordered.append(upper)

    for stat, _ in sorted(ability_scores.items(), key=lambda pair: pair[1], reverse=True):
        if stat not in ordered:
            ordered.append(stat)

    for stat in ABILITY_ORDER:
        if stat not in ordered:
            ordered.append(stat)

    return ordered


def choose_ability_scores(
    class_data: dict[str, Any],
    role: RoleLiteral | None,
    description: str | None,
    seed: int | None,
    priority_stats: list[str] | None = None,
) -> tuple[dict[str, int], list[str]]:
    weights = _build_ability_weights(class_data, role, description, priority_stats)
    candidates = point_buy_arrays(27)
    best_score: float | None = None
    best_candidates: list[tuple[int, int, int, int, int, int]] = []

    for candidate in candidates:
        score = sum(
            weights[ability] * value
            for ability, value in zip(ABILITY_ORDER, candidate, strict=True)
        )
        if best_score is None or score > best_score:
            best_score = score
            best_candidates = [candidate]
        elif score == best_score:
            best_candidates.append(candidate)

    if not best_candidates:
        msg = "Не удалось подобрать допустимые значения point-buy"
        raise RuntimeError(msg)

    rng = random.Random(seed)
    picked = rng.choice(best_candidates)
    ability_scores = tuple_to_ability_scores(picked)

    sorted_by_score = sorted(
        ability_scores.items(),
        key=lambda item: (item[1], weights[item[0]]),
        reverse=True,
    )
    top = sorted_by_score[:3]
    decisions = [
        f"Point-buy: выбрана характеристика {ability}={value} по весам класса/роли"
        for ability, value in top
    ]
    return ability_scores, decisions


def choose_skills(
    proficiency_choices: list[dict[str, Any]],
    ability_mods: dict[str, int],
    role: RoleLiteral | None,
    seed: int | None,
    desired_skills: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    selected: list[str] = []
    decisions: list[str] = []
    desired = {skill.casefold() for skill in (desired_skills or [])}

    for choice in proficiency_choices:
        choose_n = int(choice.get("choose", 0))
        if choose_n <= 0 and isinstance(choice.get("from"), dict):
            choose_n = int(choice["from"].get("choose", 0))
        if choose_n <= 0:
            continue

        skills = extract_skill_names_from_choice(choice)
        if not skills:
            continue

        scored: list[tuple[str, float, str]] = []
        for skill in skills:
            ability = SKILL_TO_ABILITY.get(skill)
            score = float(ability_mods.get(ability, 0))
            if role in ROLE_SKILL_BONUS:
                score += ROLE_SKILL_BONUS[role].get(skill, 0.0)
            if skill.casefold() in desired:
                score += 2.5
            scored.append((skill, score, ability or "неизвестно"))

        scored.sort(key=lambda item: (-item[1], item[0]))

        picked_here: list[tuple[str, float, str]] = []
        i = 0
        while i < len(scored) and len(picked_here) < choose_n:
            same_score_block = [scored[i]]
            j = i + 1
            while j < len(scored) and scored[j][1] == scored[i][1]:
                same_score_block.append(scored[j])
                j += 1
            rng.shuffle(same_score_block)
            for candidate in same_score_block:
                if candidate[0] in selected:
                    continue
                picked_here.append(candidate)
                if len(picked_here) >= choose_n:
                    break
            i = j

        for skill, _, ability in picked_here:
            selected.append(skill)
            reason = f"Выбран навык {skill} (лучшая синергия с {ability})"
            if skill.casefold() in desired:
                reason += " с учётом предпочтения из LLM"
            decisions.append(reason)

    return selected, decisions


def apply_asi(
    ability_scores: dict[str, int],
    class_levels: list[dict[str, Any]],
    target_level: int,
    priority_stats: list[str] | None,
) -> tuple[dict[str, int], list[AsiHistoryEntry], list[str]]:
    scores = ability_scores.copy()
    order = _priority_order(scores, priority_stats)
    main_stat = order[0] if order else "STR"

    asi_history: list[AsiHistoryEntry] = []
    decisions: list[str] = []

    for level_obj in class_levels:
        level_number = int(level_obj.get("level", 0))
        if level_number <= 0 or level_number > target_level:
            continue

        raw_points = level_obj.get("ability_score_bonuses", 0)
        points = int(raw_points) if isinstance(raw_points, int) else 0
        if points <= 0:
            continue

        applied: dict[str, int] = {}
        reason = ""

        while points >= 2:
            if scores.get(main_stat, 0) <= 18:
                scores[main_stat] += 2
                applied[main_stat] = applied.get(main_stat, 0) + 2
                reason = f"+2 к основной характеристике {main_stat}"
            elif scores.get("CON", 0) <= 18:
                scores["CON"] += 2
                applied["CON"] = applied.get("CON", 0) + 2
                reason = "+2 к CON"
            else:
                candidates = [stat for stat in order if scores.get(stat, 0) < 20]
                if not candidates:
                    break
                first = candidates[0]
                second = candidates[1] if len(candidates) > 1 else None
                scores[first] += 1
                applied[first] = applied.get(first, 0) + 1
                if second and scores.get(second, 0) < 20:
                    scores[second] += 1
                    applied[second] = applied.get(second, 0) + 1
                reason = f"разделено +1/+1 в {first} и {second or first}"
            points -= 2

        if points == 1:
            one_point_target = next((stat for stat in order if scores.get(stat, 0) < 20), None)
            if one_point_target is not None:
                scores[one_point_target] += 1
                applied[one_point_target] = applied.get(one_point_target, 0) + 1
                reason = f"оставшийся +1 в {one_point_target}"

        for stat in ABILITY_ORDER:
            scores[stat] = min(20, scores.get(stat, 0))

        if applied:
            entry = AsiHistoryEntry(level=level_number, applied=applied, reason=reason)
            asi_history.append(entry)
            decisions.append(f"ASI на уровне {level_number}: {applied}")

    return scores, asi_history, decisions


def _equipment_item_score(
    detail: dict[str, Any],
    role: RoleLiteral | None,
    dex_mod: int,
    str_mod: int,
) -> tuple[float, str]:
    name = str(detail.get("name", detail.get("index", "предмет")))
    offense = 0.0
    defense = 0.0
    utility = 0.0
    reason = "полезность"

    if isinstance(detail.get("damage"), dict):
        dice = detail["damage"].get("damage_dice")
        offense = average_damage_from_dice(dice)
        if offense > 0:
            reason = f"урон {dice}"

    armor_class = detail.get("armor_class")
    if isinstance(armor_class, dict):
        base = float(armor_class.get("base", 0))
        category = str(detail.get("armor_category", "")).lower()
        if "shield" in category:
            shield_bonus = float(armor_class.get("bonus", armor_class.get("base", 0)))
            defense += shield_bonus
            reason = f"бонус щита +{int(shield_bonus)}"
        else:
            dex_allowed = bool(armor_class.get("dex_bonus", True))
            max_bonus = armor_class.get("max_bonus")
            dex_part = dex_mod if dex_allowed else 0
            if isinstance(max_bonus, int):
                dex_part = min(dex_part, max_bonus)
            defense += base + dex_part
            reason = f"КД от брони {int(base + dex_part)}"

    if (
        role == "skills"
        and "tool" in str(detail.get("equipment_category", {}).get("name", "")).lower()
    ):
        utility += 1.0
        reason = "полезность для навыков"

    properties = detail.get("properties")
    if isinstance(properties, list):
        property_names = {
            str(prop.get("name", "")).lower() for prop in properties if isinstance(prop, dict)
        }
        if dex_mod >= str_mod and (
            "finesse" in property_names or detail.get("weapon_range") == "Ranged"
        ):
            offense += 0.5

    if role == "damage":
        score = offense * 2.0 + defense * 0.4 + utility * 0.2
    elif role == "tank":
        score = defense * 2.0 + offense * 0.4 + utility * 0.2
    elif role == "control":
        score = offense * 0.8 + defense * 0.6 + utility * 0.4
    elif role == "support":
        score = defense * 1.0 + offense * 0.6 + utility * 0.8
    elif role == "skills":
        score = utility * 2.0 + offense * 0.7 + defense * 0.7
    else:
        score = offense + defense + utility

    return score, f"{name}: {reason}"


def _bundle_score(
    bundle: EquipmentBundle,
    details_by_url: dict[str, dict[str, Any]],
    role: RoleLiteral | None,
    dex_mod: int,
    str_mod: int,
) -> tuple[float, str]:
    total_score = 0.0
    reasons: list[str] = []

    for item in bundle.items:
        detail = details_by_url.get(item.url)
        if not detail:
            continue
        score, reason = _equipment_item_score(detail, role, dex_mod, str_mod)
        total_score += score * item.quantity
        reasons.append(reason)

    return total_score, "; ".join(reasons)


def _merge_equipment_items(items: list[EquipmentRef]) -> list[EquipmentItem]:
    merged: dict[str, EquipmentItem] = {}
    for item in items:
        if item.index in merged:
            merged[item.index].quantity += item.quantity
        else:
            merged[item.index] = EquipmentItem(
                index=item.index,
                name=item.name,
                quantity=item.quantity,
                url=item.url,
            )
    return sorted(merged.values(), key=lambda eq: eq.index)


class CharacterGenerator:
    def __init__(self, dnd_client: DndApiClient, llm_service: LLMService | None = None):
        self.dnd_client = dnd_client
        self.llm_service = llm_service

    async def _resolve_equipment_details(
        self,
        refs: list[EquipmentRef],
    ) -> dict[str, dict[str, Any]]:
        urls = sorted({item.url for item in refs if item.url})
        if not urls:
            return {}

        tasks = [self.dnd_client.get_by_url(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        details_by_url: dict[str, dict[str, Any]] = {}
        for url, payload in zip(urls, responses, strict=True):
            if isinstance(payload, dict):
                details_by_url[url] = payload
        return details_by_url

    @staticmethod
    def _default_base_url_for_backend(backend: str) -> str:
        return "http://localhost:11434" if backend == "ollama" else "http://localhost:8001"

    def _is_llm_enabled(self, spec: CharacterSpec, llm_service: LLMService | None) -> bool:
        if spec.llm_config and spec.llm_config.enabled is not None:
            return spec.llm_config.enabled
        if spec.use_llm is not None:
            return spec.use_llm
        return bool(llm_service and llm_service.enabled)

    def _create_request_llm_service(
        self, spec: CharacterSpec
    ) -> tuple[LLMService | None, bool]:
        if spec.llm_config is None:
            return self.llm_service, False

        env_config = llm_config_from_env()
        backend = spec.llm_config.backend or env_config.backend
        if backend not in {"ollama", "openai"}:
            msg = f"Неподдерживаемый LLM-бэкенд: {backend}"
            raise ValueError(msg)

        base_url = (
            (spec.llm_config.base_url or "").strip()
            or (env_config.base_url or "").strip()
            or self._default_base_url_for_backend(backend)
        )
        model = (spec.llm_config.model or env_config.model or "").strip()
        timeout_seconds = (
            spec.llm_config.timeout_seconds
            if spec.llm_config.timeout_seconds is not None
            else env_config.timeout_seconds
        )
        enabled = self._is_llm_enabled(spec, self.llm_service)

        provider = None
        if enabled and model:
            if backend == "ollama":
                provider = OllamaProvider(
                    base_url=base_url,
                    model=model,
                    timeout_seconds=timeout_seconds,
                )
            else:
                provider = OpenAICompatibleProvider(
                    base_url=base_url,
                    model=model,
                    timeout_seconds=timeout_seconds,
                )

        cache = self.llm_service.cache if self.llm_service is not None else None
        request_service = LLMService(
            enabled=enabled,
            backend=backend,
            model=model,
            provider=provider,
            cache=cache,
        )
        return request_service, True

    async def _choose_equipment(
        self,
        class_data: dict[str, Any],
        role: RoleLiteral | None,
        ability_mods: dict[str, int],
        seed: int | None,
        selected_equipment_choices: list[str] | None = None,
    ) -> tuple[EquipmentBlock, list[dict[str, Any]], list[str]]:
        starting_equipment, option_choices = build_equipment_choices(class_data)
        options_by_group: dict[str, list[EquipmentOptionChoice]] = {}
        group_order: list[str] = []
        for choice in option_choices:
            if choice.group_id not in options_by_group:
                options_by_group[choice.group_id] = []
                group_order.append(choice.group_id)
            options_by_group[choice.group_id].append(choice)
        options_by_id = {choice.option_id: choice for choice in option_choices}

        all_refs = starting_equipment.copy()
        for choice in option_choices:
            all_refs.extend(choice.bundle.items)

        details_by_url = await self._resolve_equipment_details(all_refs)
        rng = random.Random(seed)

        chosen_refs = list(starting_equipment)
        choices_explained: list[str] = []
        decisions: list[str] = []

        selected_by_group: dict[str, list[EquipmentOptionChoice]] = {}
        manual_mode = selected_equipment_choices is not None
        if manual_mode:
            selected_ids = [
                choice.strip() for choice in selected_equipment_choices or [] if choice.strip()
            ]
            if len(selected_ids) != len(set(selected_ids)):
                msg = "Список выбора снаряжения содержит повторяющиеся идентификаторы"
                raise ValueError(msg)

            for selected_id in selected_ids:
                selected_option = options_by_id.get(selected_id)
                if selected_option is None:
                    msg = f"Недопустимый вариант снаряжения: {selected_id}"
                    raise ValueError(msg)
                selected_by_group.setdefault(selected_option.group_id, []).append(selected_option)

            for group_id in group_order:
                group_options = options_by_group[group_id]
                if not group_options:
                    continue
                choose_n = group_options[0].choose
                selected_count = len(selected_by_group.get(group_id, []))
                if selected_count != choose_n:
                    group_name = group_options[0].group_description or group_id
                    msg = (
                        f"Для блока снаряжения '{group_name}' нужно выбрать {choose_n}, "
                        f"сейчас выбрано {selected_count}"
                    )
                    raise ValueError(msg)

        for group_id in group_order:
            group_options = options_by_group[group_id]
            if not group_options:
                continue
            choose_n = group_options[0].choose

            if manual_mode:
                selected_bundles: list[tuple[EquipmentBundle, str]] = [
                    (option.bundle, "ручной выбор")
                    for option in selected_by_group.get(group_id, [])
                ]
            else:
                scored_bundles: list[tuple[EquipmentBundle, float, str]] = []
                for option in group_options:
                    score, reason = _bundle_score(
                        option.bundle,
                        details_by_url,
                        role,
                        ability_mods.get("DEX", 0),
                        ability_mods.get("STR", 0),
                    )
                    scored_bundles.append((option.bundle, score, reason))

                scored_bundles.sort(key=lambda item: item[1], reverse=True)
                selected_scored: list[tuple[EquipmentBundle, float, str]] = []
                i = 0
                while i < len(scored_bundles) and len(selected_scored) < choose_n:
                    same_score = [scored_bundles[i]]
                    j = i + 1
                    while j < len(scored_bundles) and scored_bundles[j][1] == scored_bundles[i][1]:
                        same_score.append(scored_bundles[j])
                        j += 1
                    rng.shuffle(same_score)
                    for bundle_record in same_score:
                        selected_scored.append(bundle_record)
                        if len(selected_scored) >= choose_n:
                            break
                    i = j
                selected_bundles = [(bundle, reason) for bundle, _, reason in selected_scored]

            for bundle, reason in selected_bundles:
                for item in bundle.items:
                    chosen_refs.append(item)
                item_names = format_bundle_label(bundle)
                explanation = f"Выбран вариант [{item_names}]"
                if reason:
                    explanation += f": {reason}"
                group_desc = group_options[0].group_description
                if group_desc:
                    explanation += f" (блок: {group_desc})"
                choices_explained.append(explanation)
                if manual_mode:
                    decisions.append(f"Снаряжение выбрано вручную: {item_names}")
                else:
                    decisions.append(f"Снаряжение выбрано автоматически: {item_names}")

        merged_items = _merge_equipment_items(chosen_refs)
        selected_details: list[dict[str, Any]] = []
        for item in merged_items:
            if item.url and item.url in details_by_url:
                selected_details.append(details_by_url[item.url])

        return (
            EquipmentBlock(items=merged_items, choices_explained=choices_explained),
            selected_details,
            decisions,
        )

    async def _resolve_preferences(
        self,
        spec: CharacterSpec,
        llm_service: LLMService | None,
    ) -> tuple[PreferenceExtraction, list[str]]:
        decisions: list[str] = []
        if not spec.description:
            return PreferenceExtraction(), decisions

        llm_enabled = self._is_llm_enabled(spec, llm_service)
        if not llm_enabled or llm_service is None:
            return heuristic_preferences(spec.description), decisions

        extracted = await llm_service.extract_preferences(spec.description)
        if extracted is None:
            decisions.append("Не удалось извлечь предпочтения через LLM, применена эвристика")
            return heuristic_preferences(spec.description), decisions

        decisions.append("Предпочтения успешно извлечены через LLM")
        return extracted, decisions

    async def _generate_backstory(
        self,
        spec: CharacterSpec,
        preferences: PreferenceExtraction,
        ability_scores: dict[str, int],
        skills: list[str],
        llm_service: LLMService | None,
    ) -> str | None:
        if not spec.description or llm_service is None:
            return None

        llm_enabled = self._is_llm_enabled(spec, llm_service)
        if not llm_enabled:
            return None

        summary = (
            f"Класс={spec.class_index}; Уровень={spec.level}; "
            f"Роль={spec.role or preferences.role}; "
            f"Характеристики={ability_scores}; Навыки={skills}"
        )
        return await llm_service.generate_backstory(
            description=spec.description,
            sheet_summary=summary,
            tone_tags=preferences.tone_tags,
        )

    async def generate(self, spec: CharacterSpec) -> CharacterSheet:
        llm_service, close_llm_after = self._create_request_llm_service(spec)
        try:
            class_data = await self.dnd_client.get_class(spec.class_index)
            class_levels = await self.dnd_client.get_class_levels(spec.class_index)

            preferences, preference_decisions = await self._resolve_preferences(spec, llm_service)
            role = spec.role or preferences.role

            ability_scores, ability_decisions = choose_ability_scores(
                class_data=class_data,
                role=role,
                description=spec.description,
                seed=spec.seed,
                priority_stats=preferences.priority_stats,
            )

            ability_scores, asi_history, asi_decisions = apply_asi(
                ability_scores=ability_scores,
                class_levels=class_levels,
                target_level=spec.level,
                priority_stats=preferences.priority_stats,
            )

            modifiers = {
                ability: ability_modifier(score) for ability, score in ability_scores.items()
            }

            skills, skill_decisions = choose_skills(
                proficiency_choices=[
                    choice
                    for choice in class_data.get("proficiency_choices", [])
                    if isinstance(choice, dict)
                ],
                ability_mods=modifiers,
                role=role,
                seed=spec.seed,
                desired_skills=preferences.desired_skills,
            )

            equipment, selected_equipment_details, equipment_decisions = (
                await self._choose_equipment(
                class_data=class_data,
                role=role,
                ability_mods=modifiers,
                seed=spec.seed,
                selected_equipment_choices=spec.selected_equipment_choices,
                )
            )

            hit_die = int(class_data.get("hit_die", 8))
            hp_total = calculate_level_hp(spec.level, hit_die, modifiers["CON"])
            hp_explanation = (
                f"HP = (кость хитов {hit_die} + мод CON {modifiers['CON']}) + "
                f"({spec.level - 1}) * (({hit_die}//2 + 1) + {modifiers['CON']})"
            )

            ac, ac_explanation = estimate_ac_from_items(
                selected_equipment_details,
                modifiers["DEX"],
            )
            ac_lower = ac_explanation.lower()
            ac_decisions: list[str] = []
            if "неожидан" in ac_lower:
                ac_decisions.append(
                    "При расчёте КД часть данных снаряжения имела нестандартную структуру"
                )

            backstory = await self._generate_backstory(
                spec,
                preferences,
                ability_scores,
                skills,
                llm_service,
            )

            derived = DerivedStats(
                prof_bonus=proficiency_bonus(spec.level),
                hp=hp_total,
                hp_explanation=hp_explanation,
                ac=ac,
                ac_explanation=ac_explanation,
            )

            decisions = (
                preference_decisions
                + ability_decisions
                + asi_decisions
                + skill_decisions
                + equipment_decisions
                + ac_decisions
            )
            if backstory is None and spec.description and self._is_llm_enabled(spec, llm_service):
                decisions.append("Не удалось сгенерировать предысторию, возвращено значение null")
            if not decisions:
                decisions.append("Для этого класса SRD не содержит дополнительных вариантов выбора")

            return CharacterSheet(
                class_index=spec.class_index,
                level=spec.level,
                ability_scores=ability_scores,
                modifiers=modifiers,
                proficiencies=ProficiencyBlock(skills=skills),
                equipment=equipment,
                derived=derived,
                asi_history=asi_history,
                backstory=backstory,
                decisions=decisions,
            )
        finally:
            if close_llm_after and llm_service is not None:
                await llm_service.close()
