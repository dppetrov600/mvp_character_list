from __future__ import annotations

from functools import lru_cache
from itertools import product

from app.core.rules import ABILITY_ORDER

POINT_BUY_COSTS: dict[int, int] = {
    8: 0,
    9: 1,
    10: 2,
    11: 3,
    12: 4,
    13: 5,
    14: 7,
    15: 9,
}


@lru_cache(maxsize=4)
def point_buy_arrays(total_points: int = 27) -> tuple[tuple[int, int, int, int, int, int], ...]:
    values = tuple(POINT_BUY_COSTS.keys())
    valid: list[tuple[int, int, int, int, int, int]] = []

    for candidate in product(values, repeat=6):
        cost = sum(POINT_BUY_COSTS[val] for val in candidate)
        if cost == total_points:
            valid.append(candidate)

    return tuple(valid)


def point_buy_cost(scores: tuple[int, int, int, int, int, int]) -> int:
    return sum(POINT_BUY_COSTS[val] for val in scores)


def tuple_to_ability_scores(scores: tuple[int, int, int, int, int, int]) -> dict[str, int]:
    return {ability: value for ability, value in zip(ABILITY_ORDER, scores, strict=True)}
