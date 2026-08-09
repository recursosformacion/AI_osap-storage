from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

VOTE_MIN = 1
VOTE_MAX = 5
# m: nº mínimo de votos para confianza plena. Prior bayesiano del suavizado.
ADJUSTMENT_MIN_VOTES = 5


@dataclass
class Vote:
    """Voto de un usuario sobre una obra, una vez al día (vote_day en UTC)."""

    user_id: str
    work_id: int
    vote: int
    vote_day: date
    voted_at: datetime | None = None
    id: int | None = None


@dataclass(frozen=True)
class WorkStatistics:
    """Estadísticas derivadas de una obra (datos calculados, no fuente).

    - rating: media de sus votos.
    - adjusted_rating: media suavizada hacia la media global (m votos).
    - work_count: 1.
    - confidence: min(1, vote_count / m).
    """

    work_id: int
    rating: float | None = None
    adjusted_rating: float | None = None
    vote_count: int = 0
    work_count: int = 1
    confidence: float | None = None
    calculated_at: datetime | None = None


@dataclass(frozen=True)
class ComposerStatistics:
    """Valoración agregada de un compositor (compositor canónico activo).

    - rating: media ponderada de los adjusted_rating de sus Works, ponderada por
      sqrt(vote_count) de cada Work.
    - work_count: número de Works con composer_id = este compositor.
    - confidence: min(1, vote_count / m).
    """

    composer_id: str
    rating: float | None = None
    adjusted_rating: float | None = None
    vote_count: int = 0
    work_count: int = 0
    confidence: float | None = None
    calculated_at: datetime | None = None


@dataclass
class StatisticsRun:
    """Registro de una ejecución del proceso nocturno de recálculo."""

    started_at: datetime | None = None
    finished_at: datetime | None = None
    works_updated: int = 0
    composers_updated: int = 0
    id: int | None = None
