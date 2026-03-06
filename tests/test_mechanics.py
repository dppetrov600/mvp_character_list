from app.core.optimizer import apply_asi
from app.core.rules import calculate_level_hp, estimate_ac_from_items


def test_asi_applies_on_asi_levels_and_caps_at_20():
    initial = {"STR": 8, "DEX": 15, "CON": 14, "INT": 13, "WIS": 12, "CHA": 10}
    levels = [
        {"level": 1, "ability_score_bonuses": 0},
        {"level": 4, "ability_score_bonuses": 2},
        {"level": 8, "ability_score_bonuses": 2},
        {"level": 12, "ability_score_bonuses": 2},
    ]

    updated, history, _ = apply_asi(
        ability_scores=initial,
        class_levels=levels,
        target_level=12,
        priority_stats=["DEX"],
    )

    assert updated["DEX"] == 19
    assert all(score <= 20 for score in updated.values())
    assert [entry.level for entry in history] == [4, 8, 12]


def test_hp_scaling_uses_fixed_average_rule():
    hp = calculate_level_hp(level=5, hit_die=10, con_mod=2)
    # 1st: 10+2=12; levels 2-5: 4 * (10//2+1+2)=4*8
    assert hp == 44


def test_ac_calculation_with_armor_and_shield():
    items = [
        {
            "name": "Chain Shirt",
            "armor_category": "Medium",
            "armor_class": {"base": 13, "dex_bonus": True, "max_bonus": 2},
        },
        {
            "name": "Shield",
            "armor_category": "Shield",
            "armor_class": {"base": 2, "bonus": 2, "dex_bonus": False, "max_bonus": None},
        },
    ]

    ac, _ = estimate_ac_from_items(items, dex_mod=3)
    assert ac == 17


def test_ac_fallback_without_armor():
    ac, explanation = estimate_ac_from_items([], dex_mod=2)
    assert ac == 12
    assert "10 + мод DEX" in explanation
