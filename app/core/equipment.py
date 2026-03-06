from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.data.mappers import (
    EquipmentBundle,
    EquipmentRef,
    parse_equipment_option_group,
    parse_starting_equipment,
)


@dataclass(frozen=True)
class EquipmentOptionChoice:
    option_id: str
    group_id: str
    group_index: int
    option_index: int
    choose: int
    group_description: str
    bundle: EquipmentBundle


def format_equipment_ref(ref: EquipmentRef) -> dict[str, str | int]:
    return {
        "index": ref.index,
        "name": ref.name,
        "quantity": ref.quantity,
        "url": ref.url,
    }


def format_bundle_label(bundle: EquipmentBundle) -> str:
    if not bundle.items:
        return "Без предметов"
    parts: list[str] = []
    for item in bundle.items:
        if item.quantity > 1:
            parts.append(f"{item.name} x{item.quantity}")
        else:
            parts.append(item.name)
    return ", ".join(parts)


def build_equipment_choices(
    class_data: dict[str, Any],
) -> tuple[list[EquipmentRef], list[EquipmentOptionChoice]]:
    starting_equipment = parse_starting_equipment(class_data.get("starting_equipment", []))

    choices: list[EquipmentOptionChoice] = []
    group_index = 0
    for raw_group in class_data.get("starting_equipment_options", []):
        if not isinstance(raw_group, dict):
            continue
        group = parse_equipment_option_group(raw_group)
        group_id = f"group-{group_index}"
        for option_index, bundle in enumerate(group.bundles):
            option_id = f"{group_id}-option-{option_index}"
            choices.append(
                EquipmentOptionChoice(
                    option_id=option_id,
                    group_id=group_id,
                    group_index=group_index,
                    option_index=option_index,
                    choose=group.choose,
                    group_description=group.desc,
                    bundle=bundle,
                )
            )
        group_index += 1

    return starting_equipment, choices


def build_equipment_reference_payload(
    class_index: str,
    class_data: dict[str, Any],
) -> dict[str, Any]:
    starting_equipment, choices = build_equipment_choices(class_data)

    grouped: dict[str, dict[str, Any]] = {}
    for choice in choices:
        if choice.group_id not in grouped:
            grouped[choice.group_id] = {
                "group_id": choice.group_id,
                "description": choice.group_description,
                "choose": choice.choose,
                "options": [],
            }

        grouped[choice.group_id]["options"].append(
            {
                "option_id": choice.option_id,
                "label": format_bundle_label(choice.bundle),
                "equipment_indices": [item.index for item in choice.bundle.items],
                "items": [format_equipment_ref(item) for item in choice.bundle.items],
            }
        )

    return {
        "class_index": class_index,
        "starting_equipment": [format_equipment_ref(item) for item in starting_equipment],
        "option_groups": list(grouped.values()),
    }
