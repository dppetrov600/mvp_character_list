from app.core.optimizer import choose_ability_scores
from app.core.point_buy import point_buy_arrays, point_buy_cost


def test_point_buy_arrays_are_valid():
    arrays = point_buy_arrays(27)
    assert arrays
    for candidate in arrays:
        assert len(candidate) == 6
        assert all(8 <= score <= 15 for score in candidate)
        assert point_buy_cost(candidate) == 27


def test_choose_ability_scores_favors_fighter_strength_profile():
    class_data = {
        "index": "fighter",
        "saving_throws": [{"index": "str"}, {"index": "con"}],
        "spellcasting": None,
    }

    ability_scores, _ = choose_ability_scores(class_data, role="damage", description=None, seed=42)

    assert ability_scores["STR"] >= 14
    assert ability_scores["CON"] >= 13
