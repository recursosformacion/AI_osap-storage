"""Pasada de matching de obras contra el Maestro Composer (osap-storage es el escritor).

Lee las obras de la BD objetivo (por defecto la réplica local `osap-storage`),
las resuelve UNA A UNA con el pipeline existente (osap-api resolve, solo
lectura) y escribe en las tablas del Maestro mediante los repositorios de
osap-storage:

- Composer ya existe (por alias, nombre o identificador) -> asocia la obra
  (works.composer_id) y works_count queda derivado (COUNT).
- Composer NO existe pero la evidencia del proveedor es sólida
  (MBID/VIAF/ISNI/IPI/QID/IMSLP o combinación) -> CREA el Composer (idempotente
  por SELECT previo de identificador; active/visible=1), con aliases,
  identificadores y evidencia (rule `250k-create`), y asocia la obra.
- Evidencia insuficiente / ambiguous / contradictoria -> no crea; conserva la
  atribución y la registra en la cola de candidatos.
- Anonymous/Traditional -> nunca entidad Composer.

Idempotente: se omite una obra si ya está asociada a un Composer del Maestro o
si ya figura en el checkpoint. Reanudable con `--checkpoint` y `--from-id`.
`--dry-run` no escribe nada.

Uso:
    python scripts/run_works_matching.py --db osap-storage \
        --api http://127.0.0.1:8001 --limit 200 \
        --checkpoint data/works_matching_run.jsonl [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.entities.composer import Composer, ComposerStatus  # noqa: E402
from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402
from infrastructure.repositories.sql_composer_repository import SqlComposerRepository  # noqa: E402

PIPELINE_VERSION = "osap-api-resolve-v1"
MATCHER_VERSION = "works-matching-0.1.0"
ANONYMOUS = frozenset({
    "anon", "anon.", "anonymous", "anonymus", "anonimo", "anónimo", "trad", "trad.",
    "traditional", "traditionnel", "tradicional", "traditionell", "unattributed",
    "unknown", "author unknown", "urheber unbekannt", "urheber unbek.",
    "na", "n/a", "n.a.", "none", "unknown composer", "composer",
})
STRONG_ID_TYPES = {"mbid", "viaf", "isni", "ipi", "qid", "imslp"}
_ID_CANON = {"mbid": "mbid", "musicbrainz": "mbid", "viaf": "viaf",
             "wikidata": "qid", "wikidata_qid": "qid", "isni": "isni",
             "ipi": "ipi", "imslp": "imslp"}
_NS = uuid.UUID("6f1b3c2e-4f5a-4b6c-9d8e-7a0b1c2d3e4f")


def _norm(name: str | None) -> str:
    """Normalización coherente con composer_aliases.normalized_alias (minúsculas,
    colapso de espacios; conserva acentos/puntuación como el Maestro)."""
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def _is_anon(name: str | None) -> bool:
    low = re.sub(r"[?¿¡!.]+\s*$", "", (name or "").strip().lower())
    return low in ANONYMOUS or low.startswith("urheber unbekannt")


def _id_type(raw: str) -> str | None:
    return _ID_CANON.get((raw or "").lower())


class ResolveClient:
    def __init__(self, base_url: str, timeout: int = 120) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def resolve(self, work: dict) -> tuple[int, dict]:
        payload = {
            "work": {"title": work.get("title"), "catalog": work.get("catalogue"),
                     "year": None},
            "composer": {"name": work.get("composer")} if work.get("composer") else None,
            "source": {"provider": "pdmx", "source_work_id": str(work["id"])},
            "representations": [{"title": work.get("title"), "provider": "pdmx",
                                 "format": "musicxml"}],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base}/api/v1/composers/resolve", data=data, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                return resp.status, json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            return exc.code, {}
        except Exception as exc:  # noqa: BLE001
            return 0, {"network_error": str(exc)}


class Matcher:
    """Clasificación + escritura (repositorios de osap-storage)."""

    def __init__(self, repo: SqlComposerRepository, db: Database) -> None:
        self._repo = repo
        self._db = db

    async def canonical(self, composer: Composer) -> Composer:
        seen = set()
        c = composer
        while c.status == ComposerStatus.MERGED and c.merged_into and c.merged_into not in seen:
            seen.add(c.merged_into)
            nxt = await self._repo.get_by_id(c.merged_into)
            if nxt is None:
                break
            c = nxt
        return c

    async def find_provider_composer(self, name: str, identifiers: dict[str, str]) -> list[Composer]:
        found: dict[str, Composer] = {}
        by_alias = await self._repo.resolve_by_normalized(_norm(name))
        if by_alias:
            c = await self._repo.get_by_id(by_alias[0])
            if c:
                found[c.id] = await self.canonical(c)
        by_name = await self._repo.get_by_name(name)
        if by_name:
            found[by_name.id] = await self.canonical(by_name)
        for raw, value in identifiers.items():
            id_type = _id_type(raw)
            if not id_type or not value:
                continue
            for c in await self._repo.find_by_identifier(id_type, str(value)):
                found[c.id] = await self.canonical(c)
        return list(found.values())

    async def create_and_link(self, work_id: int, name: str,
                              identifiers: dict[str, str]) -> Composer:
        strong = [(raw, _id_type(raw)) for raw in identifiers if _id_type(raw) in STRONG_ID_TYPES]
        anchor = strong[0] if strong else None
        cid = uuid.uuid5(_NS, f"250k:{anchor[1]}:{identifiers[anchor[0]]}") if anchor else str(uuid.uuid4())
        composer = Composer(id=str(cid), name=name, status=ComposerStatus.ACTIVE,
                            visible=True, review_status="not_reviewed", source_system="maestro")
        await self._repo.create(composer)
        await self._repo.add_alias(cid, name, _norm(name))
        for raw, value in identifiers.items():
            id_type = _id_type(raw)
            if not id_type:
                continue
            await self._repo.add_identifier(
                str(cid), id_type, str(value),
                is_identity_anchor=(anchor is not None and raw == anchor[0]),
                source="provider",
                strength="strong" if id_type in STRONG_ID_TYPES else None,
                channels=[f"provider:{raw}"])
        await self._repo.add_evidence(
            str(cid), rule="250k-create", decision="auto", reason="provider_evidence",
            anchor_type=anchor[1] if anchor else "none",
            anchor_value=identifiers[anchor[0]] if anchor else "none",
            identifiers_used=[{"id_type": id_type, "id_value": v}
                              for id_type, v in identifiers.items()],
            matcher_version=MATCHER_VERSION)
        return composer

    async def associate(self, work_id: int, composer_id: str) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE works SET composer_id = %s, updated_at = NOW(6) WHERE id = %s",
                (composer_id, work_id))

    def classify(self, work_status: str | None, name: str | None,
                 identifiers: dict[str, str]) -> dict:
        """Decisión por obra (sin escribir). Devuelve la clasificación."""
        if not name or _is_anon(name):
            return {"composer_match": "not_applicable", "composer": None}
        strong = any(_id_type(r) in STRONG_ID_TYPES and v for r, v in identifiers.items())
        if work_status == "resolved" and strong:
            return {"composer_match": "create_solid", "composer": None}
        return {"composer_match": "no_match", "composer": None}


def _provider_identifiers(candidates: list, provider_name: str | None) -> dict[str, str]:
    if not provider_name:
        return {}
    target = _norm(provider_name)
    ids: dict[str, str] = {}
    for c in candidates if isinstance(candidates, list) else []:
        if not isinstance(c, dict):
            continue
        if _norm(c.get("name") or "") != target:
            continue
        ext = c.get("external_ids") or {}
        if isinstance(ext, dict):
            ids.update({str(k): str(v) for k, v in ext.items()})
    return ids


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("OSAP_CONFIG", str(ROOT / "config.yaml")))
    parser.add_argument("--db", default=None, help="BD objetivo (por defecto la de la config)")
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument("--workers", type=int, default=10, help="concurrencia (obras en paralelo)")
    parser.add_argument("--from-id", type=int, default=0, help="reanudar desde este id de obra")
    parser.add_argument("--checkpoint", default=str(ROOT / "data" / "works_matching_run.jsonl"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base = Settings()  # type: ignore[call-arg]
    settings = base.model_copy(update={"db_name": args.db or base.db_name})
    db = Database(settings)
    repo = SqlComposerRepository(db)
    client = ResolveClient(args.api)
    matcher = Matcher(repo, db)

    checkpoint_path = Path(args.checkpoint)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    done: set[int] = set()
    if checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            with contextlib.suppress(ValueError, KeyError):
                done.add(int(json.loads(line)["work_id"]))

    run_id = f"250k-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    stats: Counter = Counter()
    created: list[dict] = []
    candidates: list[dict] = []

    async def run() -> None:
        last_id = args.from_id
        processed = 0
        t0 = time.time()
        sem = asyncio.Semaphore(args.workers)
        lock = asyncio.Lock()

        async def checkpoint(wid: int, status: str, composer_id: str | None = None,
                             visible: bool | None = None, cs: str | None = None) -> None:
            async with lock:
                _checkpoint(checkpoint_path, run_id, wid, status, composer_id, visible, cs)

        async def process(row: dict) -> None:
            wid = int(row["id"])
            title = row.get("title")
            composer = row.get("composer")
            catalogue = row.get("catalogue")
            if not (title or "").strip():
                stats["no_title"] += 1
                await checkpoint(wid, "no_title", None)
                return
            # idempotencia: ¿ya asociada a un Composer del Maestro?
            async with db.connection() as conn, conn.cursor() as cur:
                await cur.execute("SELECT composer_id FROM works WHERE id = %s", (wid,))
                current = (await cur.fetchone() or {}).get("composer_id")
            if current:
                existing = await repo.get_by_id(current)
                if existing and existing.status != ComposerStatus.MERGED:
                    stats["already_associated"] += 1
                    await checkpoint(wid, "already_associated", current)
                    return
            status_code, doc = await asyncio.to_thread(
                client.resolve, {"id": wid, "title": title, "composer": composer, "catalogue": catalogue}
            )
            if status_code != 200:
                stats["errors"] += 1
                await checkpoint(wid, "error", None)
                return
            data = doc.get("data") or {} if isinstance(doc, dict) else {}
            work_status = data.get("status")
            candidates_raw = data.get("candidates") or []
            provider_ids = _provider_identifiers(candidates_raw, composer)
            decision = matcher.classify(work_status, composer, provider_ids)
            stats["status_" + str(work_status)] += 1
            stats["match_" + decision["composer_match"]] += 1

            if decision["composer_match"] == "not_applicable":
                await checkpoint(wid, decision["composer_match"], None)
                return
            if decision["composer_match"] == "no_match":
                candidates.append({"work_id": wid, "provider_composer": composer,
                                   "provider_identifiers": provider_ids})
                await checkpoint(wid, "no_match", None)
                return

            # create_solid: SELECT previo antes de crear
            found = await matcher.find_provider_composer(composer, provider_ids)
            if len(found) == 1:
                c = found[0]
                stats["matched_existing"] += 1
                if not args.dry_run:
                    await matcher.associate(wid, c.id)
                await checkpoint(wid, "matched_existing", c.id, c.visible, c.status)
                return
            if len(found) > 1:
                stats["ambiguous_maestro"] += 1
                candidates.append({"work_id": wid, "provider_composer": composer,
                                   "provider_identifiers": provider_ids, "ambiguous": True})
                await checkpoint(wid, "ambiguous_maestro", None)
                return
            if work_status != "resolved":
                stats["work_not_resolved_no_create"] += 1
                candidates.append({"work_id": wid, "provider_composer": composer,
                                   "provider_identifiers": provider_ids})
                await checkpoint(wid, "no_create_not_resolved", None)
                return
            stats["composer_created"] += 1
            new_c = None
            if not args.dry_run:
                new_c = await matcher.create_and_link(wid, composer, provider_ids)
                await matcher.associate(wid, new_c.id)
            created.append({"work_id": wid, "provider_composer": composer,
                            "provider_identifiers": provider_ids,
                            "composer_id": str(new_c.id) if new_c else "DRY-RUN",
                            "works_count": 1})
            await checkpoint(wid, "composer_created", str(new_c.id) if new_c else None)
            print(f"  work {wid}: {work_status} | {decision['composer_match']} | "
                  f"{composer or '-'}", flush=True)

        async def bounded(row: dict) -> None:
            async with sem:
                await process(row)

        while processed < args.limit:
            async with db.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, title, composer, catalogue FROM works "
                    "WHERE id > %s ORDER BY id LIMIT %s", (last_id, args.batch))
                rows = await cur.fetchall()
            if not rows:
                break
            pending: list[dict] = []
            for row in rows:
                if processed >= args.limit:
                    break
                processed += 1
                wid = int(row["id"])
                last_id = wid
                if wid in done:
                    continue
                pending.append(row)
            if pending:
                await asyncio.gather(*(bounded(r) for r in pending))
            if processed >= args.limit:
                break

        print("\n=== ESTADÍSTICAS (pasada obras) ===")
        print(json.dumps(dict(stats), ensure_ascii=False, indent=1))
        print(f"creados ({len(created)}):")
        for item in sorted(created, key=lambda x: x["work_id"]):
            print("  ", item)
        out = {"run_id": run_id, "dry_run": args.dry_run,
               "pipeline_version": PIPELINE_VERSION, "matcher_version": MATCHER_VERSION,
               "stats": dict(stats), "created": created, "candidates": candidates,
               "elapsed_seconds": round(time.time() - t0, 2)}
        out_path = checkpoint_path.with_name(
            f"works_matching_stats_{run_id}.json")
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"-> {out_path} | checkpoint: {checkpoint_path}")
        await db.close()

    asyncio.run(run())
    return 0


def _checkpoint(path: Path, run_id: str, work_id: int, status: str,
                composer_id: str | None, visible: bool | None = None,
                composer_status: str | None = None) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": run_id, "work_id": work_id, "status": status,
                            "composer_id": composer_id, "visible": visible,
                            "composer_status": composer_status}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
