#!/usr/bin/env python
"""Ingiere obras de IMSLP (Worklist API) como metadatos en `works` (osap-storage).

Materializa cada obra de IMSLP como una fila de `works` con `works_origin='IMSLP'` y
`works_origin_id` = **pageid** de IMSLP (numérico, estable), guardando además:
  - `works_title`        = título de la obra
  - `works_catalogue`    = nº de catálogo/incipit (`icatno`) si lo trae
  - `works_source_url`   = permalink a la página de IMSLP (**enlace a la fuente**; IMSLP
    NO se redistribuye: no se descargan ni alojan ficheros)
  - una fila `works_person_import` (role='composer', source='imslp'), SIN resolver

Es **idempotente e incremental en la escritura**: omite las obras ya presentes (mismo
`works_origin_id`), así que puede ejecutarse semanalmente para incorporar solo las novedades.
OJO: el **barrido es completo** en cada ejecución (la Worklist no ofrece filtro por fecha ni
reanudación por pageid: se pagina desde `start=0` hasta el final). Pensado para programarse
con un timer systemd. La resolución a personas canónicas y la indexación se hacen después con
los scripts habituales (`resolve_index_composers`, `rebuild_index`).

Uso (venv de osap-storage, desde la raíz del repo):
    python -m scripts.import_imslp_works --limit 50              # dry-run
    python -m scripts.import_imslp_works --apply --limit 500
    python -m scripts.import_imslp_works --db osap_storage --apply   # prod
"""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import time
import urllib.request
from collections.abc import Iterator

from infrastructure.config import Settings
from infrastructure.db.connection import Database

_IMSLP_API = "https://imslp.org/imslpscripts/API.ISCR.php"
_USER_AGENT = "OSAP/1.1 (+https://openmusicrepository.com)"


def _reverse_last_first(name: str) -> str:
    """'Ferrari, Carlotta' -> 'Carlotta Ferrari' (el índice usa el nombre natural)."""
    name = (name or "").strip()
    if "," not in name:
        return name
    last, _, first = name.partition(",")
    return f"{first.strip()} {last.strip()}".strip()


def _parse_entry(entry: object) -> dict[str, object] | None:
    """Normaliza una entrada del Worklist. `None` si no es utilizable (sin título/pageid)."""
    if not isinstance(entry, dict):
        return None
    iv = entry.get("intvals") or {}
    if not isinstance(iv, dict):
        return None
    title = str(iv.get("worktitle") or "").strip()
    pageid = str(iv.get("pageid") or "").strip()
    if not title or not pageid:
        return None
    return {
        "pageid": pageid,
        "title": title,
        "composer": _reverse_last_first(str(iv.get("composer") or "")) or None,
        "catalogue": str(iv.get("icatno") or "").strip() or None,
        "source_url": str(entry.get("permlink") or "").strip() or None,
    }


def _iter_imslp(start: int, limit: int, verify_ssl: bool = True) -> Iterator[dict[str, object]]:
    """Obras de IMSLP vía Worklist API, paginada por `start` (type=2, sort=id)."""
    ctx = None if verify_ssl else ssl._create_unverified_context()  # noqa: S323
    n = 0
    while limit <= 0 or n < limit:
        url = (
            f"{_IMSLP_API}?account=worklist/disclaimer=accepted/sort=id/type=2/"
            f"start={start}/retformat=json"
        )
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                doc = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001 — best-effort: corta la página y termina
            print(f"  imslp error start={start}: {exc}", flush=True)
            break
        meta = doc.get("metadata") if isinstance(doc, dict) else None
        more = bool(meta.get("moreresultsavailable")) if isinstance(meta, dict) else False
        keys = [k for k in (doc or {}) if k != "metadata"]
        if not keys:
            break
        for key in keys:
            rec = _parse_entry(doc[key])
            if rec is None:
                continue
            yield rec
            n += 1
            if limit > 0 and n >= limit:
                return
        if not more:
            break
        start += len(keys)
        time.sleep(0.5)


async def _ingest(db_name: str, apply: bool, start: int, limit: int, verify_ssl: bool) -> None:
    settings = Settings().model_copy(update={"db_name": db_name})  # type: ignore[call-arg]
    db = Database(settings)
    await db.connect()

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT works_origin_id FROM works WHERE works_origin = 'IMSLP'")
        existing = {str(row["works_origin_id"]) for row in await cur.fetchall()}

    added = skipped = 0
    async with db.connection() as conn, conn.cursor() as cur:
        for rec in _iter_imslp(start, limit, verify_ssl):
            pageid = str(rec["pageid"])
            if pageid in existing:
                skipped += 1
                continue
            existing.add(pageid)
            if not apply:
                added += 1
                continue
            await cur.execute(
                "INSERT INTO works "
                "(works_origin, works_origin_id, works_title, works_catalogue, works_source_url) "
                "VALUES ('IMSLP', %s, %s, %s, %s)",
                (pageid, rec["title"], rec["catalogue"], rec["source_url"]),
            )
            work_id = cur.lastrowid
            if rec["composer"]:
                await cur.execute(
                    "INSERT INTO works_person_import "
                    "(works_id, works_person_import_name, works_person_import_role, "
                    " works_person_import_source) VALUES (%s, %s, 'composer', 'imslp')",
                    (work_id, rec["composer"]),
                )
            added += 1
            if added % 1000 == 0:
                await conn.commit()
                print(f"  ... {added} works", flush=True)
        if apply:
            await conn.commit()

    await db.close()
    modo = "APPLY" if apply else "DRY-RUN"
    print(f"works IMSLP [{modo}]: +{added} | ya presentes: {skipped}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--apply", action="store_true", help="escribe (por defecto dry-run)")
    ap.add_argument("--start", type=int, default=0, help="offset de paginación del Worklist")
    ap.add_argument("--limit", type=int, default=0, help="máximo de obras (0 = todas)")
    ap.add_argument("--no-imslp-verify-ssl", dest="verify_ssl", action="store_false",
                    help="no verificar el TLS de IMSLP (solo para dry-run local; en Prod verificar)")
    args = ap.parse_args()
    asyncio.run(_ingest(args.db, args.apply, args.start, args.limit, args.verify_ssl))


if __name__ == "__main__":
    main()
