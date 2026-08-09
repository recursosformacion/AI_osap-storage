from __future__ import annotations

from uuid import uuid4

from domain.entities.composer import (
    Composer,
    ComposerAlias,
    ComposerDetail,
    ComposerStatus,
    ComposerSummary,
    ComposerWorkRef,
    MergeComposersResult,
)
from domain.exceptions import DuplicateComposerAlias, EntityNotFound, InvalidMerge
from domain.ports.composer_repository import ComposerRepository
from domain.services.composer_names import normalize_composer_name

from infrastructure.db.connection import Database


def _row_to_composer(row: dict) -> Composer:
    return Composer(
        id=row["id"],
        name=row["name"],
        status=row.get("status") or ComposerStatus.ACTIVE,
        merged_into=row.get("merged_into"),
        merged_at=row.get("merged_at"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _row_to_alias(row: dict) -> ComposerAlias:
    return ComposerAlias(
        id=row["id"],
        composer_id=row["composer_id"],
        alias=row["alias"],
        normalized_alias=row["normalized_alias"],
        created_at=row["created_at"],
    )


class SqlComposerRepository(ComposerRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, composer: Composer) -> Composer:
        if not composer.id:
            composer.id = str(uuid4())
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO composers (id, name, status, merged_into) VALUES (%s, %s, %s, %s)",
                (composer.id, composer.name, composer.status, composer.merged_into),
            )
            return composer

    async def get_by_id(self, composer_id: str) -> Composer | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM composers WHERE id = %s", (composer_id,))
            row = await cur.fetchone()
            return _row_to_composer(row) if row else None

    async def add_alias(self, composer_id: str, alias: str, normalized_alias: str) -> ComposerAlias:
        try:
            async with self._db.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO composer_aliases (composer_id, alias, normalized_alias) "
                    "VALUES (%s, %s, %s)",
                    (composer_id, alias, normalized_alias),
                )
                await cur.execute(
                    "SELECT * FROM composer_aliases WHERE id = %s", (cur.lastrowid,)
                )
                return _row_to_alias(await cur.fetchone())
        except Exception as exc:
            if self._is_duplicate(exc):
                raise DuplicateComposerAlias(normalized_alias) from None
            raise

    async def list_aliases(self, composer_id: str) -> list[ComposerAlias]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM composer_aliases WHERE composer_id = %s ORDER BY id",
                (composer_id,),
            )
            return [_row_to_alias(row) for row in await cur.fetchall()]

    async def resolve_by_normalized(self, normalized: str) -> tuple[str, str] | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT a.normalized_alias AS norm, c.id, c.name, c.status, c.merged_into "
                "FROM composer_aliases a JOIN composers c ON c.id = a.composer_id "
                "WHERE a.normalized_alias = %s LIMIT 1",
                (normalized,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return await self._canonical_of(conn, row["id"], row)

    async def resolve_many_by_normalized(
        self, normalized: list[str]
    ) -> dict[str, tuple[str, str]]:
        if not normalized:
            return {}
        placeholders = ", ".join(["%s"] * len(normalized))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT a.normalized_alias AS norm, c.id, c.name, c.status, c.merged_into "
                "FROM composer_aliases a JOIN composers c ON c.id = a.composer_id "
                f"WHERE a.normalized_alias IN ({placeholders})",
                normalized,
            )
            rows = await cur.fetchall()
        canonical = await self._canonical_map([r["id"] for r in rows])
        return {r["norm"]: canonical[r["id"]] for r in rows if r["id"] in canonical}

    async def list_summaries(
        self, *, limit: int, offset: int, q: str | None = None
    ) -> list[ComposerSummary]:
        where = ["c.status = %s"]
        params: list = [ComposerStatus.ACTIVE]
        if q and (q := q.strip()):
            norm = normalize_composer_name(q)
            where.append(
                "(c.name LIKE %s OR EXISTS ("
                "SELECT 1 FROM composer_aliases a WHERE a.composer_id = c.id AND a.normalized_alias LIKE %s))"
            )
            params.extend([f"%{q}%", f"%{norm}%"])
        where_sql = " AND ".join(where)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT c.id, c.name, c.status, "
                "(SELECT COUNT(*) FROM composer_aliases a WHERE a.composer_id = c.id) AS aliases_count, "
                "(SELECT COUNT(*) FROM works w WHERE w.composer_id = c.id) AS works_count "
                f"FROM composers c WHERE {where_sql} "
                "ORDER BY c.name LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            return [
                ComposerSummary(
                    id=r["id"],
                    name=r["name"],
                    status=r["status"],
                    aliases_count=int(r["aliases_count"] or 0),
                    works_count=int(r["works_count"] or 0),
                )
                for r in await cur.fetchall()
            ]

    async def count(self, q: str | None = None) -> int:
        where = ["status = %s"]
        params: list = [ComposerStatus.ACTIVE]
        if q and (q := q.strip()):
            norm = normalize_composer_name(q)
            where.append(
                "(name LIKE %s OR EXISTS ("
                "SELECT 1 FROM composer_aliases a WHERE a.composer_id = composers.id AND a.normalized_alias LIKE %s))"
            )
            params.extend([f"%{q}%", f"%{norm}%"])
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT COUNT(*) AS total FROM composers WHERE {' AND '.join(where)}", params
            )
            return int((await cur.fetchone())["total"])

    async def get_detail(self, composer_id: str) -> ComposerDetail | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, status, merged_into, merged_at, created_at, updated_at "
                "FROM composers WHERE id = %s",
                (composer_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            await cur.execute(
                "SELECT alias FROM composer_aliases WHERE composer_id = %s ORDER BY id",
                (composer_id,),
            )
            aliases = [r["alias"] for r in await cur.fetchall()]
            await cur.execute(
                "SELECT COUNT(*) AS total FROM works WHERE composer_id = %s", (composer_id,)
            )
            works_count = int((await cur.fetchone())["total"])
            return ComposerDetail(
                id=row["id"],
                name=row["name"],
                status=row["status"],
                aliases=aliases,
                works_count=works_count,
                merged_into=row["merged_into"],
                merged_at=row["merged_at"],
            )

    async def list_works(
        self, composer_id: str, *, limit: int, offset: int
    ) -> list[ComposerWorkRef]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT id AS work_id, title, composer_id FROM works "
                "WHERE composer_id = %s ORDER BY id LIMIT %s OFFSET %s",
                (composer_id, limit, offset),
            )
            return [
                ComposerWorkRef(
                    work_id=r["work_id"], title=r["title"], composer_id=r["composer_id"]
                )
                for r in await cur.fetchall()
            ]

    async def merge(
        self, target_id: str, source_ids: list[str], *, merged_by: str | None = None
    ) -> MergeComposersResult:
        ids: list[str] = list(dict.fromkeys(source_ids))
        if not ids:
            raise InvalidMerge("source_ids cannot be empty")
        if target_id in ids:
            raise InvalidMerge("target cannot appear among source_ids")

        operation_id = str(uuid4())
        async with self._db.transaction() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name, status FROM composers WHERE id = %s", (target_id,)
            )
            target = await cur.fetchone()
            if target is None:
                raise EntityNotFound("composer", target_id)
            if target["status"] == ComposerStatus.MERGED:
                raise InvalidMerge(f"target composer {target_id} is already merged")

            placeholders = ", ".join(["%s"] * len(ids))
            await cur.execute(
                f"SELECT id, status, merged_into FROM composers WHERE id IN ({placeholders})",
                ids,
            )
            found = {r["id"]: r for r in await cur.fetchall()}
            for sid in ids:
                if sid not in found:
                    raise EntityNotFound("composer", sid)

            to_merge: list[str] = []
            for sid in ids:
                s = found[sid]
                if s["status"] == ComposerStatus.MERGED:
                    if s["merged_into"] == target_id:
                        continue  # idempotente: ya fusionado en target
                    raise InvalidMerge(
                        f"source composer {sid} is already merged into {s['merged_into']}"
                    )
                to_merge.append(sid)

            if not to_merge:
                return MergeComposersResult(
                    target_id=target_id,
                    sources_merged=[],
                    aliases_transferred=0,
                    works_moved=0,
                    merge_operation_id=operation_id,
                )

            mph = ", ".join(["%s"] * len(to_merge))

            await cur.execute(
                f"UPDATE composer_aliases SET composer_id = %s WHERE composer_id IN ({mph})",
                [target_id, *to_merge],
            )
            aliases_transferred = cur.rowcount

            await cur.execute(
                f"UPDATE works SET composer_id = %s WHERE composer_id IN ({mph})",
                [target_id, *to_merge],
            )
            works_moved = cur.rowcount

            await cur.execute(
                f"UPDATE composers SET status = %s, merged_into = %s, merged_at = NOW(6) "
                f"WHERE id IN ({mph})",
                [ComposerStatus.MERGED, target_id, *to_merge],
            )

            for sid in to_merge:
                await cur.execute(
                    "INSERT INTO composer_merge_history "
                    "(merge_operation_id, source_composer_id, target_composer_id, merged_by) "
                    "VALUES (%s, %s, %s, %s)",
                    (operation_id, sid, target_id, merged_by),
                )

        return MergeComposersResult(
            target_id=target_id,
            sources_merged=to_merge,
            aliases_transferred=aliases_transferred,
            works_moved=works_moved,
            merge_operation_id=operation_id,
        )

    async def _canonical_of(self, conn, composer_id: str, first_row: dict) -> tuple[str, str]:
        canonical = await self._canonical_map([composer_id])
        if composer_id not in canonical:
            # No debería ocurrir (el alias ya apunta a un compositor), defensivo.
            return first_row["id"], first_row["name"]
        return canonical[composer_id]

    async def _canonical_map(
        self, composer_ids: list[str]
    ) -> dict[str, tuple[str, str]]:
        """Devuelve para cada id su compositor activo final, siguiendo merged_into."""
        if not composer_ids:
            return {}
        unique: list[str] = list(dict.fromkeys(composer_ids))
        result: dict[str, tuple[str, str]] = {}
        async with self._db.connection() as conn, conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(unique))
            await cur.execute(
                f"SELECT id, name, status, merged_into FROM composers WHERE id IN ({placeholders})",
                unique,
            )
            rows = {r["id"]: r for r in await cur.fetchall()}
        for cid in unique:
            final_id, final_name = cid, None
            seen: set[str] = set()
            current = rows.get(cid)
            while current is not None and current["status"] == ComposerStatus.MERGED:
                if current["id"] in seen or not current["merged_into"]:
                    break
                seen.add(current["id"])
                target = rows.get(current["merged_into"])
                if target is None:
                    async with self._db.connection() as conn, conn.cursor() as cur:
                        await cur.execute(
                            "SELECT id, name, status, merged_into FROM composers WHERE id = %s",
                            (current["merged_into"],),
                        )
                        t = await cur.fetchone()
                    if t is None:
                        break
                    rows[t["id"]] = t
                    target = t
                current = target
            if current is not None and current["status"] != ComposerStatus.MERGED:
                final_id = current["id"]
                final_name = current["name"]
            if final_name is not None:
                result[cid] = (final_id, final_name)
        return result

    def _is_duplicate(self, exc: Exception) -> bool:
        code = getattr(exc, "args", (None,))
        if code and code[0] in (1062, 23000):
            return True
        return "Duplicate entry" in str(exc)
