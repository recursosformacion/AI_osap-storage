from __future__ import annotations

import json
from collections import defaultdict

from domain.entities.resolution import AxisValues, ResourceEvidence
from domain.ports.resolution_source import ResolutionSource

from infrastructure.db.connection import Database


def _voicing(raw: str | None) -> tuple[str, ...]:
    """Acepta el CSV de `GROUP_CONCAT` (actual) o un JSON array (histórico)."""
    if not raw:
        return ()
    text = str(raw).strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return tuple(part.strip() for part in text.split(",") if part.strip())
    if isinstance(data, list):
        return tuple(str(item).strip() for item in data if str(item).strip())
    return (str(data).strip(),) if str(data).strip() else ()


def _canonical(person_id: str | None, merged: dict[str, str]) -> str | None:
    seen: set[str] = set()
    while person_id is not None and person_id in merged and person_id not in seen:
        seen.add(person_id)
        person_id = merged[person_id]
    return person_id


async def _axes(cur, join: str, expr: str, work_ids: list[int]) -> dict[int, list[str]]:
    placeholders = ", ".join(["%s"] * len(work_ids))
    await cur.execute(
        f"SELECT wi.works_id AS wid, GROUP_CONCAT({expr} ORDER BY {expr} SEPARATOR '|') AS v "
        f"FROM {join} WHERE wi.works_id IN ({placeholders}) GROUP BY wi.works_id",
        work_ids,
    )
    return {
        row["wid"]: (row["v"].split("|") if row["v"] else [])
        for row in await cur.fetchall()
    }


class SqlResolutionSource(ResolutionSource):
    """Carga la evidencia (recursos + representación + obra + ejes) en una sola pasada."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self, work_id: int, *, candidate_limit: int = 50) -> list[ResourceEvidence]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT id, works_title FROM works WHERE id = %s", (work_id,))
            target = await cur.fetchone()
            if target is None:
                return []

            work_ids: list[int] = [work_id]
            if target["works_title"]:
                await cur.execute(
                    "SELECT id FROM works WHERE works_title = %s AND id <> %s ORDER BY id LIMIT %s",
                    (target["works_title"], work_id, candidate_limit),
                )
                work_ids.extend(row["id"] for row in await cur.fetchall())

            placeholders = ", ".join(["%s"] * len(work_ids))
            await cur.execute(
                "SELECT res.id AS resource_id, res.works_resources_type AS resource_type, "
                "r.id AS representation_id, "
                "COALESCE(r.representations_origin, w.works_origin) AS origin, "
                "COALESCE(r.representations_origin_id, w.works_key) AS origin_id, "
                "COALESCE(r.representations_license, w.works_license) AS license, "
                "w.id AS work_id, w.works_title AS title, "
                "w.works_catalogue AS catalogue, w.works_musical_key AS musical_key, "
                "(SELECT GROUP_CONCAT(DISTINCT e.ensembles_code ORDER BY e.ensembles_code "
                "SEPARATOR ', ') FROM work_ensembles we JOIN ensembles e "
                "ON e.id = we.ensembles_id WHERE we.works_id = w.id) AS voicing, "
                "(SELECT p.persons_name FROM works_person_roles rp "
                " JOIN persons p ON p.persons_id = rp.works_person_roles_person_id "
                " WHERE rp.works_person_roles_work_id = w.id "
                " AND rp.works_person_roles_role_id = 1 LIMIT 1) AS composer, "
                "(SELECT rp.works_person_roles_person_id FROM works_person_roles rp "
                " WHERE rp.works_person_roles_work_id = w.id "
                " AND rp.works_person_roles_role_id = 1 "
                " ORDER BY rp.works_person_roles_order, rp.works_person_roles_id LIMIT 1) AS composer_id "
                "FROM works_resources res "
                "JOIN works w ON w.id = res.works_resources_work_id "
                "LEFT JOIN representations r ON r.id = res.works_resources_representation_id "
                f"WHERE res.works_resources_work_id IN ({placeholders}) "
                "ORDER BY res.works_resources_work_id, res.id",
                work_ids,
            )
            rows = await cur.fetchall()
            if not rows:
                return []

            rep_ids = sorted(
                {row["representation_id"] for row in rows if row["representation_id"] is not None}
            )
            editors: dict[int, list[str]] = defaultdict(list)
            if rep_ids:
                rep_placeholders = ", ".join(["%s"] * len(rep_ids))
                await cur.execute(
                    "SELECT representation_persons_representation_id AS rep_id, "
                    "representation_persons_name AS name FROM representation_persons "
                    f"WHERE representation_persons_representation_id IN ({rep_placeholders})",
                    rep_ids,
                )
                for row in await cur.fetchall():
                    editors[row["rep_id"]].append(row["name"])

            person_ids = sorted({row["composer_id"] for row in rows if row["composer_id"]})
            canonical: dict[str, str] = {}
            aliases_by_person: dict[str, list[str]] = defaultdict(list)
            if person_ids:
                person_ph = ", ".join(["%s"] * len(person_ids))
                await cur.execute(
                    "SELECT persons_id, persons_merged_into FROM persons "
                    f"WHERE persons_id IN ({person_ph})",
                    person_ids,
                )
                merged = {
                    r["persons_id"]: r["persons_merged_into"]
                    for r in await cur.fetchall()
                }
                for person_id in person_ids:
                    canonical[person_id] = _canonical(person_id, merged) or person_id
                await cur.execute(
                    "SELECT person_id, person_aliases_normalized_alias FROM persons_aliases "
                    f"WHERE person_id IN ({person_ph})",
                    person_ids,
                )
                for row in await cur.fetchall():
                    aliases_by_person[row["person_id"]].append(
                        row["person_aliases_normalized_alias"]
                    )

            instruments = await _axes(
                cur,
                "work_instruments wi JOIN instruments x ON x.id = wi.instruments_id",
                "x.name_en",
                work_ids,
            )
            ensembles = await _axes(
                cur,
                "work_ensembles wi JOIN ensembles x ON x.id = wi.ensembles_id",
                "x.ensembles_code",
                work_ids,
            )
            languages = await _axes(
                cur,
                "work_language wi JOIN languages x ON x.id = wi.languages_id",
                "x.languages_name",
                work_ids,
            )

        return [
            ResourceEvidence(
                resource_id=row["resource_id"],
                resource_type=row["resource_type"] or "",
                representation_id=row["representation_id"],
                origin=row["origin"] or "",
                origin_id=row["origin_id"],
                license=row["license"] or "",
                editors=tuple(sorted(editors.get(row["representation_id"], []))),
                work_id=row["work_id"],
                title=row["title"],
                catalogue=row["catalogue"],
                composer=row["composer"],
                composer_id=canonical.get(row["composer_id"], row["composer_id"]),
                composer_aliases=tuple(
                    sorted(aliases_by_person.get(row["composer_id"], []))
                ),
                axes=AxisValues(
                    voicing=_voicing(row["voicing"]),
                    ensembles=tuple(ensembles.get(row["work_id"], [])),
                    instruments=tuple(instruments.get(row["work_id"], [])),
                    languages=tuple(languages.get(row["work_id"], [])),
                    key=row["musical_key"],
                ),
            )
            for row in rows
        ]
