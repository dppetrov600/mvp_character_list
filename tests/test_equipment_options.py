from app.data.mappers import parse_equipment_option_group


def test_equipment_options_parser_handles_multiple_and_counted_reference():
    option = {
        "choose": 1,
        "desc": "Weapon package",
        "from": {
            "option_set_type": "options_array",
            "options": [
                {
                    "option_type": "reference",
                    "item": {
                        "index": "longsword",
                        "name": "Longsword",
                        "url": "/api/equipment/longsword",
                    },
                },
                {
                    "option_type": "multiple",
                    "items": [
                        {
                            "option_type": "reference",
                            "item": {
                                "index": "shortbow",
                                "name": "Shortbow",
                                "url": "/api/equipment/shortbow",
                            },
                        },
                        {
                            "option_type": "counted_reference",
                            "count": 20,
                            "of": {
                                "index": "arrows",
                                "name": "Arrows",
                                "url": "/api/equipment/arrows",
                            },
                        },
                    ],
                },
            ],
        },
    }

    group = parse_equipment_option_group(option)

    assert group.choose == 1
    assert len(group.bundles) == 2

    bundle_sizes = sorted(len(bundle.items) for bundle in group.bundles)
    assert bundle_sizes == [1, 2]

    arrows_bundle = next(
        bundle for bundle in group.bundles if any(i.index == "arrows" for i in bundle.items)
    )
    arrows = next(item for item in arrows_bundle.items if item.index == "arrows")
    assert arrows.quantity == 20
