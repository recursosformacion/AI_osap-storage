from __future__ import annotations

from datetime import UTC, datetime

from domain.entities.voting import (
    ADJUSTMENT_MIN_VOTES,
    VOTE_MAX,
    VOTE_MIN,
    ComposerStatistics,
    StatisticsRun,
    Vote,
    WorkStatistics,
)
from domain.exceptions import DuplicateVote, EntityNotFound
from domain.ports.voting_repository import VotingRepository

from infrastructure.db.connection import Database


def _row_to_work_stats(row: dict) -> WorkStatistics:
    def _f(key: str) -> float | None:
        val = row.get(key)
        return float(val) if val is not None else None

    return WorkStatistics(
        work_id=row["work_id"],
        rating=_f("rating"),
        adjusted_rating=_f("adjusted_rating"),
        vote_count=int(row["vote_count"] or 0),
        work_count=int(row.get("work_count") or 1),
        confidence=_f("confidence"),
        calculated_at=row.get("calculated_at"),
    )


def _row_to_composer_stats(row: dict) -> ComposerStatistics:
    def _f(key: str) -> float | None:
        val = row.get(key)
        return float(val) if val is not None else None

    return ComposerStatistics(
        composer_id=row["composer_id"],
        rating=_f("rating"),
        adjusted_rating=_f("adjusted_rating"),
        vote_count=int(row["vote_count"] or 0),
        work_count=int(row.get("work_count") or 0),
        confidence=_f("confidence"),
        calculated_at=row.get("calculated_at"),
    )


class SqlVotingRepository(VotingRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add_vote(self, user_id: str, work_id: int, vote: int) -> Vote:
        if vote < VOTE_MIN or vote > VOTE_MAX:
            raise ValueError(f"vote must be between {VOTE_MIN} and {VOTE_MAX}")
        vote_day = datetime.now(UTC).date()
        try:
            async with self._db.connection() as conn, conn.cursor() as cur:
                await cur.execute("SELECT id FROM works WHERE id = %s", (work_id,))
                if await cur.fetchone() is None:
                    raise EntityNotFound("work", work_id)
                await cur.execute(
                    "INSERT INTO votes (user_id, work_id, vote, vote_day) VALUES (%s, %s, %s, %s)",
                    (user_id, work_id, vote, vote_day.isoformat()),
                )
                await cur.execute("SELECT * FROM votes WHERE id = %s", (cur.lastrowid,))
                row = await cur.fetchone()
                return Vote(
                    id=row["id"],
                    user_id=row["user_id"],
                    work_id=row["work_id"],
                    vote=row["vote"],
                    vote_day=row["vote_day"],
                    voted_at=row["voted_at"],
                )
        except Exception as exc:
            if self._is_duplicate(exc):
                raise DuplicateVote(user_id, work_id) from None
            raise

    async def get_work_statistics(self, work_id: int) -> WorkStatistics | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT work_id, rating, adjusted_rating, vote_count, work_count, "
                "confidence, calculated_at FROM work_statistics WHERE work_id = %s",
                (work_id,),
            )
            row = await cur.fetchone()
            return _row_to_work_stats(row) if row else None

    async def get_work_statistics_bulk(self, work_ids: list[int]) -> dict[int, WorkStatistics]:
        if not work_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(work_ids))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT work_id, rating, adjusted_rating, vote_count, work_count, "
                f"confidence, calculated_at FROM work_statistics WHERE work_id IN ({placeholders})",
                work_ids,
            )
            return {r["work_id"]: _row_to_work_stats(r) for r in await cur.fetchall()}

    async def get_composer_statistics(self, composer_id: str) -> ComposerStatistics | None:
        # `composer_statistics` está retirado: se calcula en vivo desde
        # work_statistics + works (solo compositores activos del maestro).
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT w.composer_id, "
                "SUM(ws.adjusted_rating * SQRT(ws.vote_count)) / NULLIF(SUM(SQRT(ws.vote_count)), 0) "
                "    AS rating, "
                "SUM(ws.adjusted_rating * SQRT(ws.vote_count)) / NULLIF(SUM(SQRT(ws.vote_count)), 0) "
                "    AS adjusted_rating, "
                "COALESCE(SUM(ws.vote_count), 0) AS vote_count, "
                "COUNT(DISTINCT w.id) AS work_count, "
                "LEAST(1.0, COALESCE(SUM(ws.vote_count), 0) / %s) AS confidence, "
                "NOW(6) AS calculated_at "
                "FROM works w "
                "JOIN composers c ON c.id = w.composer_id AND c.status = 'active' "
                "LEFT JOIN work_statistics ws ON ws.work_id = w.id "
                "WHERE w.composer_id = %s "
                "GROUP BY w.composer_id",
                (ADJUSTMENT_MIN_VOTES, composer_id),
            )
            row = await cur.fetchone()
            return _row_to_composer_stats(row) if row else None

    async def recompute_all(self) -> StatisticsRun:
        m = ADJUSTMENT_MIN_VOTES
        run = StatisticsRun(started_at=datetime.now(UTC))
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute("SELECT AVG(vote) AS g FROM votes")
            row = await cur.fetchone()
            global_mean = float(row["g"]) if row and row["g"] is not None else 0.0

            # Work: media, suavizada hacia la media global, confidence.
            await cur.execute(
                "INSERT INTO work_statistics "
                "(work_id, rating, adjusted_rating, vote_count, work_count, confidence, calculated_at) "
                "SELECT v.work_id, AVG(v.vote), "
                "(COUNT(*) * AVG(v.vote) + %s * %s) / (COUNT(*) + %s), "
                "COUNT(*), 1, LEAST(1.0, COUNT(*) / %s), NOW(6) "
                "FROM votes v GROUP BY v.work_id "
                "ON DUPLICATE KEY UPDATE "
                "rating = VALUES(rating), adjusted_rating = VALUES(adjusted_rating), "
                "vote_count = VALUES(vote_count), confidence = VALUES(confidence), "
                "calculated_at = VALUES(calculated_at)",
                (m, global_mean, m, m),
            )
            works_updated = cur.rowcount
            # Limpia filas de obras que ya no tienen votos (idempotencia).
            await cur.execute(
                "DELETE ws FROM work_statistics ws LEFT JOIN votes v ON v.work_id = ws.work_id "
                "WHERE v.id IS NULL"
            )

            # Estadísticas por compositor se calculan en vivo (composer_statistics
            # retirado); no se materializa ninguna tabla de agregación.
            composers_updated = 0

            run.finished_at = datetime.now(UTC)
            run.works_updated = works_updated
            run.composers_updated = composers_updated
            await cur.execute(
                "INSERT INTO statistics_runs (started_at, finished_at, works_updated, composers_updated) "
                "VALUES (%s, %s, %s, %s)",
                (run.started_at, run.finished_at, run.works_updated, run.composers_updated),
            )
            run.id = cur.lastrowid
        return run

    def _is_duplicate(self, exc: Exception) -> bool:
        code = getattr(exc, "args", (None,))
        if code and code[0] in (1062, 23000):
            return True
        return "Duplicate entry" in str(exc)
