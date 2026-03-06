from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any


@dataclass(frozen=True)
class EquipmentRef:
    index: str
    name: str
    url: str
    quantity: int = 1


@dataclass(frozen=True)
class EquipmentBundle:
    items: tuple[EquipmentRef, ...]


@dataclass(frozen=True)
class EquipmentOptionGroup:
    choose: int
    bundles: tuple[EquipmentBundle, ...]
    desc: str = ""


def _reference_from_node(node: Any, quantity: int = 1) -> EquipmentRef | None:
    if not isinstance(node, dict):
        return None

    if {"index", "name", "url"}.issubset(node.keys()):
        url = str(node["url"])
        if "/api/equipment" in url:
            return EquipmentRef(
                index=str(node["index"]),
                name=str(node["name"]),
                url=url,
                quantity=max(1, quantity),
            )

    if "equipment" in node:
        equipment = _reference_from_node(
            node["equipment"], quantity=int(node.get("quantity", quantity))
        )
        if equipment:
            return equipment

    if "item" in node:
        item = _reference_from_node(node["item"], quantity=int(node.get("count", quantity)))
        if item:
            return item

    if "of" in node:
        item = _reference_from_node(node["of"], quantity=int(node.get("count", quantity)))
        if item:
            return item

    return None


def _merge_items(items: list[EquipmentRef]) -> tuple[EquipmentRef, ...]:
    merged: dict[str, EquipmentRef] = {}
    for item in items:
        if item.index in merged:
            existing = merged[item.index]
            merged[item.index] = EquipmentRef(
                index=existing.index,
                name=existing.name,
                url=existing.url,
                quantity=existing.quantity + item.quantity,
            )
        else:
            merged[item.index] = item
    return tuple(sorted(merged.values(), key=lambda it: it.index))


def _combine_bundle_lists(bundle_lists: list[list[EquipmentBundle]]) -> list[EquipmentBundle]:
    if not bundle_lists:
        return []

    if len(bundle_lists) == 1:
        return bundle_lists[0]

    combined: list[EquipmentBundle] = []
    for combo in product(*bundle_lists):
        aggregated: list[EquipmentRef] = []
        for bundle in combo:
            aggregated.extend(bundle.items)
        combined.append(EquipmentBundle(items=_merge_items(aggregated)))

    return combined


def _parse_choice_block(choice_block: dict[str, Any]) -> list[EquipmentBundle]:
    source = choice_block.get("from")
    if isinstance(source, list):
        bundles: list[EquipmentBundle] = []
        for entry in source:
            bundles.extend(_parse_equipment_node(entry))
        return bundles

    if isinstance(source, dict):
        if isinstance(source.get("options"), list):
            bundles = []
            for option in source["options"]:
                bundles.extend(_parse_equipment_node(option))
            return bundles

        if isinstance(source.get("items"), list):
            bundles = []
            for option in source["items"]:
                bundles.extend(_parse_equipment_node(option))
            return bundles

        return _parse_equipment_node(source)

    return []


def _parse_equipment_node(node: Any) -> list[EquipmentBundle]:
    direct = _reference_from_node(node)
    if direct:
        return [EquipmentBundle(items=(direct,))]

    if isinstance(node, list):
        bundles: list[EquipmentBundle] = []
        for item in node:
            bundles.extend(_parse_equipment_node(item))
        return bundles

    if not isinstance(node, dict):
        return []

    option_type = node.get("option_type")
    if option_type in {"reference", "counted_reference"}:
        ref = _reference_from_node(node)
        return [EquipmentBundle(items=(ref,))] if ref else []

    if option_type == "multiple":
        parts = node.get("items", [])
        parsed_parts = [_parse_equipment_node(part) for part in parts if part is not None]
        return _combine_bundle_lists(parsed_parts)

    if option_type == "choice":
        choice_data = node.get("choice")
        if isinstance(choice_data, dict):
            return _parse_choice_block(choice_data)
        return []

    if option_type == "string":
        return []

    if "choose" in node and "from" in node:
        return _parse_choice_block(node)

    if "from" in node:
        return _parse_equipment_node(node["from"])

    if "options" in node:
        return _parse_equipment_node(node["options"])

    if "items" in node:
        return _parse_equipment_node(node["items"])

    return []


def parse_starting_equipment(starting_equipment: list[dict[str, Any]]) -> list[EquipmentRef]:
    items: list[EquipmentRef] = []
    for entry in starting_equipment:
        ref = _reference_from_node(entry)
        if ref:
            items.append(ref)
    return items


def parse_equipment_option_group(option_entry: dict[str, Any]) -> EquipmentOptionGroup:
    choose = int(option_entry.get("choose", 0))
    if choose <= 0 and isinstance(option_entry.get("from"), dict):
        choose = int(option_entry["from"].get("choose", 0))
    if choose <= 0:
        choose = 1
    desc = str(option_entry.get("desc", "")).strip()
    source = option_entry.get("from", option_entry)
    bundles = _parse_equipment_node(source)

    deduped: dict[tuple[tuple[str, int], ...], EquipmentBundle] = {}
    for bundle in bundles:
        key = tuple((item.index, item.quantity) for item in bundle.items)
        deduped[key] = bundle

    return EquipmentOptionGroup(
        choose=max(1, choose),
        bundles=tuple(deduped.values()),
        desc=desc,
    )


def extract_skill_names_from_choice(choice: dict[str, Any]) -> list[str]:
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return

        if not isinstance(node, dict):
            return

        if {"index", "name"}.issubset(node.keys()):
            index = str(node["index"])
            name = str(node["name"])
            if index.startswith("skill-") or name.startswith("Skill: "):
                clean = name.replace("Skill: ", "", 1).strip()
                if clean:
                    seen.add(clean)

        for key in ("from", "options", "items", "item", "of", "choice"):
            if key in node:
                walk(node[key])

    walk(choice)
    return sorted(seen)
