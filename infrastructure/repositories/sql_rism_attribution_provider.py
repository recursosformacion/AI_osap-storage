from __future__ import annotations

from collections import defaultdict

from domain.entities.composer_attribution import (
    SOURCE_RISM,
    ComposerAttribution,
    state_for_reliability,
)
from domain.ports.composer_attribution_provider import ComposerAttributionProvider
from domain.services.composer_names import normalize_composer_name
from domain.services.title_evidence import is_attributable_title

from infrastructure.db.connection import Database


class SqlRismAttributionProvider(ComposerAttributionProvider):
    """Lee atribuciones desde el índice local `rism_sources` (read-only).

    Solo títulos «atribuibles» (>=2 tokens significativos) y con persona RISM conocida.
    Coincidencia exacta por título normalizado (uniforme `240` o transcrito `245`).
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def attribute_many(
        self, titles: list[str]
    ) -> dict[str, list[ComposerAttribution]]:
        keys: dict[str, str] = {}
        for title in titles:
            if is_attributable_title(title):
                keys[normalize_composer_name(title)] = title
        if not keys:
            return {}
        placeholders = ", ".join(["%s"] * len(keys))
        params = list(keys) + list(keys)
        where = (
            "s.rism_composer_person_id IS NOT NULL AND "
            f"(s.rism_uniform_title_norm IN ({placeholders}) "
            f"OR s.rism_title_norm IN ({placeholders}))"
        )
        canonical_sql = (
            "SELECT s.rism_uniform_title_norm AS uniform_norm, s.rism_title_norm AS title_norm, "
            "COALESCE(p.rism_canonical_id, s.rism_composer_person_id) AS person_id, "
            "s.rism_composer_name AS person_name, s.rism_reliability AS reliability "
            "FROM rism_sources s "
            "LEFT JOIN rism_persons p ON p.rism_person_id = s.rism_composer_person_id "
            f"WHERE {where}"
        )
        plain_sql = (
            "SELECT s.rism_uniform_title_norm AS uniform_norm, s.rism_title_norm AS title_norm, "
            "s.rism_composer_person_id AS person_id, s.rism_composer_name AS person_name, "
            "s.rism_reliability AS reliability FROM rism_sources s "
            f"WHERE {where}"
        )
        rows = None
        try:
            async with self._db.connection() as conn, conn.cursor() as cur:
                await cur.execute(canonical_sql, params)
                rows = await cur.fetchall()
        except Exception:  # noqa: BLE001 - 2C.1 aún no aplicada: probar sin canónico
            rows = None
        if rows is None:
            try:
                async with self._db.connection() as conn, conn.cursor() as cur:
                    await cur.execute(plain_sql, params)
                    rows = await cur.fetchall()
            except Exception:  # noqa: BLE001 - índice externo ausente: sin evidencia
                return {}

        out: dict[str, list[ComposerAttribution]] = defaultdict(list)
        for row in rows:
            for norm_title, via in ((row["uniform_norm"], "240"), (row["title_norm"], "245")):
                if norm_title and norm_title in keys:
                    out[norm_title].append(
                        ComposerAttribution(
                            person_id=row["person_id"],
                            person_name=row["person_name"],
                            state=state_for_reliability(row["reliability"]),
                            reliability=row["reliability"],
                            source=SOURCE_RISM,
                            matched_title=keys[norm_title],
                            via=via,
                        )
                    )
        return dict(out)
