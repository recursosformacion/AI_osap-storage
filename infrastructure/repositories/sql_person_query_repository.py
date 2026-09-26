"""Consultas de personas por rol para la API pública/admin de osap-storage.

Modelo nuevo: la identidad vive en `persons` y sus roles en `works_person_roles`
(`works_person_roles_role_id` → `roles.id`). La API acepta los roles por **clave inglesa**
(`composer`, `arranger`, `performer`, `editor`…), que se traducen a ids con
`domain.services.person_roles`.

Estas consultas son de **lectura** y específicas de la API (listado de personas por rol,
ficha y obras de una persona con género e instrumentos). No tocan otras aplicaciones.
"""

from __future__ import annotations

from typing import Any

from infrastructure.db.connection import Database

_ANY_ROLE = "works_person_roles_role_id IN (__ROLES__)"


def _roles_placeholder(role_ids: tuple[int, ...]) -> str:
    return ", ".join(str(int(role_id)) for role_id in role_ids)


class SqlPersonQueryRepository:
    """Lecturas de personas/obras por rol, devolviendo dicts listos para la API."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_persons(
        self,
        role_ids: tuple[int, ...],
        *,
        q: str | None,
        limit: int,
        offset: int,
        include_hidden: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        roles_sql = _roles_placeholder(role_ids)
        where: list[str] = ["p.persons_status = 'active'"]
        params: list[Any] = []
        if not include_hidden:
            where.append("p.persons_visible = 1")
        if q and q.strip():
            term = f"%{q.strip()}%"
            where.append(
                "(p.persons_name LIKE %s OR EXISTS ("
                "SELECT 1 FROM persons_aliases a WHERE a.person_id = p.persons_id "
                "AND a.person_aliases_alias LIKE %s))"
            )
            params.extend([term, term])
        where_sql = " AND ".join(where)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT COUNT(DISTINCT p.persons_id) AS total FROM persons p "
                f"WHERE {where_sql} AND EXISTS (SELECT 1 FROM works_person_roles r "
                f" WHERE r.works_person_roles_person_id = p.persons_id "
                f" AND {_ANY_ROLE.replace('__ROLES__', roles_sql)})",
                params,
            )
            total = int((await cur.fetchone())["total"] or 0)
            await cur.execute(
                "SELECT p.persons_id AS id, p.persons_name AS name, "
                "p.persons_sortname AS sort_name, p.persons_birth_year AS birth_year, "
                "p.persons_death_year AS death_year, p.persons_visible AS visible, "
                "p.persons_review_status AS review_status, "
                "p.persons_biography_summary AS biography_summary, "
                "p.persons_biography_era AS biography_era, "
                "p.persons_biography_nationality AS biography_nationality, "
                "(SELECT COUNT(*) FROM persons_aliases a WHERE a.person_id = p.persons_id) "
                "  AS aliases_count, "
                "(SELECT COUNT(DISTINCT r2.works_person_roles_work_id) "
                "   FROM works_person_roles r2 WHERE r2.works_person_roles_person_id = p.persons_id "
                f"   AND {_ANY_ROLE.replace('__ROLES__', roles_sql)}) AS works_count "
                "FROM persons p "
                f"WHERE {where_sql} AND EXISTS (SELECT 1 FROM works_person_roles r "
                f" WHERE r.works_person_roles_person_id = p.persons_id "
                f" AND {_ANY_ROLE.replace('__ROLES__', roles_sql)}) "
                "ORDER BY p.persons_name LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            items = [dict(row) for row in await cur.fetchall()]
            await self._attach_roles(cur, items)
        return items, total

    async def get_person(self, person_id: str) -> dict[str, Any] | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT p.persons_id AS id, p.persons_name AS name, "
                "p.persons_givenname AS given_name, p.persons_familyname AS family_name, "
                "p.persons_sortname AS sort_name, p.persons_birth_year AS birth_year, "
                "p.persons_death_year AS death_year, p.persons_visible AS visible, "
                "p.persons_status AS status, p.persons_review_status AS review_status, "
                "p.persons_type AS person_type, p.persons_nationality AS nationality, "
                "p.persons_image_url AS image_url, "
                "p.persons_biography_summary AS biography_summary, "
                "p.persons_biography_era AS biography_era, "
                "p.persons_biography_nationality AS biography_nationality, "
                "p.persons_biography_key_works AS biography_key_works, "
                "p.persons_biography_key_fact AS biography_key_fact "
                "FROM persons p WHERE p.persons_id = %s",
                (person_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            person = dict(row)
            await cur.execute(
                "SELECT person_aliases_alias AS alias FROM persons_aliases "
                "WHERE person_id = %s ORDER BY person_aliases_alias",
                (person_id,),
            )
            person["aliases"] = [r["alias"] for r in await cur.fetchall()]
            await self._attach_roles(cur, [person])
        return person

    async def works_for_person(
        self,
        person_id: str,
        role_ids: tuple[int, ...],
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        roles_sql = _roles_placeholder(role_ids)
        role_filter = f"AND r.works_person_roles_role_id IN ({roles_sql})"
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(DISTINCT r.works_person_roles_work_id) AS total "
                "FROM works_person_roles r WHERE r.works_person_roles_person_id = %s "
                f"{role_filter}",
                (person_id,),
            )
            total = int((await cur.fetchone())["total"] or 0)
            await cur.execute(
                "SELECT w.id AS work_id, w.works_title AS title, w.works_subtitle AS subtitle, "
                "w.works_catalogue AS catalogue, w.works_year AS year, "
                "r.works_person_roles_role_id AS role_id "
                "FROM works_person_roles r JOIN works w ON w.id = r.works_person_roles_work_id "
                "WHERE r.works_person_roles_person_id = %s "
                f"{role_filter} ORDER BY w.works_title LIMIT %s OFFSET %s",
                (person_id, limit, offset),
            )
            items = [dict(row) for row in await cur.fetchall()]
            await self._attach_work_facets(cur, items)
        for item in items:
            item["roles"] = _role_keys([item.pop("role_id", None)])
        return items, total

    async def _attach_roles(self, cur: Any, items: list[dict[str, Any]]) -> None:
        """Añade `roles` (claves inglesas) a cada persona según `works_person_roles`."""
        ids = [str(item["id"]) for item in items if item.get("id")]
        if not ids:
            return
        placeholders = ", ".join(["%s"] * len(ids))
        await cur.execute(
            "SELECT DISTINCT works_person_roles_person_id AS pid, "
            "works_person_roles_role_id AS role_id "
            f"FROM works_person_roles WHERE works_person_roles_person_id IN ({placeholders})",
            ids,
        )
        by_person: dict[str, list[int]] = {}
        for row in await cur.fetchall():
            by_person.setdefault(str(row["pid"]), []).append(int(row["role_id"]))
        for item in items:
            item["roles"] = _role_keys(by_person.get(str(item.get("id")), []))

    async def _attach_work_facets(self, cur: Any, items: list[dict[str, Any]]) -> None:
        """Añade `genres` e `instruments` a las obras de una persona."""
        work_ids = [int(item["work_id"]) for item in items if item.get("work_id") is not None]
        if not work_ids:
            return
        placeholders = ", ".join(["%s"] * len(work_ids))
        await cur.execute(
            "SELECT wg.works_id AS work_id, g.name AS name FROM work_genres wg "
            "JOIN genres g ON g.id = wg.genres_id "
            f"WHERE wg.works_id IN ({placeholders}) ORDER BY g.name",
            work_ids,
        )
        genres: dict[int, list[str]] = {}
        for row in await cur.fetchall():
            genres.setdefault(int(row["work_id"]), []).append(str(row["name"]))
        await cur.execute(
            "SELECT wi.works_id AS work_id, i.name_en AS name_en, i.name_es AS name_es, "
            "i.code AS code FROM work_instruments wi "
            "JOIN instruments i ON i.id = wi.instruments_id "
            f"WHERE wi.works_id IN ({placeholders}) ORDER BY i.sort, i.name_en",
            work_ids,
        )
        instruments: dict[int, list[str]] = {}
        for row in await cur.fetchall():
            label = row.get("name_es") or row.get("name_en") or row.get("code") or ""
            instruments.setdefault(int(row["work_id"]), []).append(str(label))
        for item in items:
            work_id = int(item["work_id"])
            item["genres"] = genres.get(work_id, [])
            item["instruments"] = instruments.get(work_id, [])


def _role_keys(role_ids: Any) -> list[str]:
    """Ids de rol → claves inglesas de la API (las desconocidas se ignoran)."""
    from domain.services.person_roles import role_key

    keys: list[str] = []
    for value in role_ids if isinstance(role_ids, list) else [role_ids]:
        if value is None:
            continue
        key = role_key(int(value))
        if key and key not in keys:
            keys.append(key)
    return keys
