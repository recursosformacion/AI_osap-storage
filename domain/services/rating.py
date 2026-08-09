from __future__ import annotations

import math

from domain.entities.voting import ADJUSTMENT_MIN_VOTES


def adjusted_rating(
    vote_count: int,
    rating: float,
    global_mean: float,
    m: int = ADJUSTMENT_MIN_VOTES,
) -> float | None:
    """Media de la obra suavizada hacia la media global (prior bayesiano).

    adjusted = (vote_count * rating + m * global_mean) / (vote_count + m)
    Con pocos votos se aproxima a global_mean; con muchos, a rating.
    """
    if vote_count <= 0:
        return None
    return (vote_count * rating + m * global_mean) / (vote_count + m)


def confidence(vote_count: int, m: int = ADJUSTMENT_MIN_VOTES) -> float:
    """Confianza 0..1 de la estimación: min(1, vote_count / m)."""
    if vote_count <= 0:
        return 0.0
    return min(1.0, vote_count / m)


def work_weight(vote_count: int) -> float:
    """Peso de una Work en la agregación de Composer: sqrt(vote_count)."""
    return math.sqrt(max(0, vote_count))


def composer_rating(work_adjusted: list[float], work_vote_count: list[int]) -> float | None:
    """Media ponderada de los adjusted_rating de las Works, ponderada por sqrt(vote_count)."""
    numerator = sum(adj * work_weight(vc) for adj, vc in zip(work_adjusted, work_vote_count, strict=True))
    denominator = sum(work_weight(vc) for vc in work_vote_count)
    if denominator <= 0:
        return None
    return numerator / denominator
