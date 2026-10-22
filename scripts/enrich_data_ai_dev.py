"""Enriquece OBRAS y PROVEEDORES con Gemini sobre la BD **local de desarrollo**.

Importante:
- Solo escribe si se pasa `--apply`; por defecto hace una pasada en seco.
- Rechaza hosts/BD que no sean de desarrollo (no usa el túnel 3307 ni producción).
- Actualiza las tablas de unión, no solo la fila principal:
  * `work_genres` (géneros existentes en `genres`)
  * `work_ensembles` (ensembles existentes)
  * `work_instruments` (instrumentos existentes)
  * `work_language` (códigos existentes)
- Los valores propuestos solo rellenan campos vacíos/NULL, salvo `--overwrite`.
- Guarda un JSONL de auditoría en `output/ai_enrich_*.jsonl`.

Uso:
    .venv\\Scripts\\python.exe scripts/enrich_data_ai_dev.py --list --mode all --limit 10
    .venv\\Scripts\\python.exe scripts/enrich_data_ai_dev.py --mode works --limit 5
    .venv\\Scripts\\python.exe scripts/enrich_data_ai_dev.py --mode all --limit 5 --apply

Claves: `GEMINI_API_KEY`, `GEMINI_API_KEY2`, `GEMINI_API_KEYS` (separadas por comas/espacios).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
_API = "https://generativelanguage.googleapis.com/v1beta/models"
_RETRY = {429, 500, 502, 503, 504}
_PROMPT = """Eres un catalogador musical. Rellena SOLO lo que puedas justificar con el título,
compositor, catálogo y fuente. No inventes datos. Devuelve JSON válido con esta forma:
{"results":[{"id":0,"confidence":0.0,"musical_key":null,"year":null,
"duration":null,"measures":null,"pages":null,"parts":null,"complexity":null,
"license":null,"description":null,"attribution_type":null,"attribution_note":null,
"genres":[],"ensembles":[],"instruments":[],"languages":[]}]}
- `id` es el id del elemento de entrada.
- `genres` debe usar nombres de la lista permitida.
- `ensembles`, `instruments` y `languages` deben usar valores de las listas permitidas.
- Si no estás seguro, deja el campo null/[] y baja `confidence`.
"""


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _db_conf() -> dict[str, Any]:
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("db") or {}
    return {
        "host": conf.get("host", "127.0.0.1"),
        "port": int(conf.get("port", 3306)),
        "user": conf.get("user"),
        "password": conf.get("password"),
        "database": conf.get("name"),
    }


def _assert_dev(conf: dict[str, Any]) -> None:
    host = str(conf.get("host", ""))
    port = int(conf.get("port", 0))
    if port == 3307 or host not in {"127.0.0.1", "localhost"}:
        raise SystemExit(f"rechazado: {host}:{port} no es la BD local de desarrollo")


def _keys() -> list[str]:
    raw: list[str] = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEY2", "GEMINI_API_KEYS"):
        value = os.environ.get(name, "")
        if value:
            raw.extend(part for part in re.split(r"[,;\s]+", value) if part)
    return list(dict.fromkeys(raw))


def _gemini(payload: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    if not keys:
        raise RuntimeError("falta GEMINI_API_KEY / GEMINI_API_KEY2")
    last: Exception | None = None
    for attempt, key in enumerate(keys * 3):
        try:
            req = urllib.request.Request(
                f"{_API}/{_MODEL}:generateContent?key={key}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            return json.loads(text)
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in _RETRY:
                raise
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(min(2**attempt, 8))
    raise RuntimeError(f"Gemini no disponible: {last}")


def _candidates(conn: pymysql.connections.Connection, limit: int) -> list[dict[str, Any]]:
    sql = """
        SELECT w.id, w.works_title, w.works_catalogue,
               GROUP_CONCAT(DISTINCT p.persons_name SEPARATOR ', ') AS composers
        FROM works w
        LEFT JOIN works_person_roles r ON r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1
        LEFT JOIN persons p ON p.persons_id = r.works_person_roles_person_id
        WHERE (w.works_musical_key IS NULL OR w.works_year IS NULL OR w.works_description IS NULL
               OR w.works_duration IS NULL OR w.works_measures IS NULL OR w.works_pages IS NULL
               OR w.works_parts IS NULL OR w.works_complexity IS NULL OR w.works_license IS NULL
               OR w.works_instrumentation IS NULL
               OR NOT EXISTS (SELECT 1 FROM work_genres g WHERE g.works_id = w.id)
               OR NOT EXISTS (SELECT 1 FROM work_ensembles e WHERE e.works_id = w.id))
        GROUP BY w.id, w.works_title, w.works_catalogue
        ORDER BY w.id
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (limit,))
        return list(cur.fetchall())


def _allowed(conn: pymysql.connections.Connection, table: str, column: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {column} AS name FROM {table} WHERE {column} IS NOT NULL")  # noqa: S608
        return [str(row["name"]) for row in cur.fetchall() if row["name"]]


def _ask_works(conn: pymysql.connections.Connection, rows: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    genres = _allowed(conn, "genres", "name")
    ensembles = _allowed(conn, "ensembles", "ensembles_name")
    instruments = _allowed(conn, "instruments", "name_en")
    languages = _allowed(conn, "languages", "languages_code")
    payload = {
        "contents": [{"parts": [{"text": _PROMPT + json.dumps({
            "works": rows,
            "allowed": {"genres": genres[:40], "ensembles": ensembles[:120],
                        "instruments": instruments[:200], "languages": languages[:200]},
        }, ensure_ascii=False)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    data = _gemini(payload, keys)
    results = data.get("results")
    if not isinstance(results, list):
        raise RuntimeError("respuesta de Gemini sin results")
    return [item for item in results if isinstance(item, dict)]


def _apply_works(conn: pymysql.connections.Connection, rows: list[dict[str, Any]], results: list[dict[str, Any]], *, overwrite: bool, min_confidence: float, log: list[dict[str, Any]]) -> None:
    by_id = {int(r["id"]): r for r in rows if str(r.get("id", "")).isdigit()}
    with conn.cursor() as cur:
        cur.execute("SELECT id, LOWER(name) AS name FROM genres")
        genres = {str(r["name"]): int(r["id"]) for r in cur.fetchall()}
        cur.execute("SELECT ensembles_id, LOWER(ensembles_name) AS name FROM ensembles")
        ensembles = {str(r["name"]): int(r["ensembles_id"]) for r in cur.fetchall()}
        cur.execute("SELECT id, LOWER(name_en) AS name FROM instruments")
        instruments = {str(r["name"]): int(r["id"]) for r in cur.fetchall() if r["name"]}
        cur.execute("SELECT id, LOWER(languages_code) AS code FROM languages")
        languages = {str(r["code"]).lower(): int(r["id"]) for r in cur.fetchall() if r["code"]}

        def upsert_join(table: str, col: str, wid: int, ids: list[int]) -> None:
            for link_id in dict.fromkeys(ids):
                cur.execute(
                    f"INSERT IGNORE INTO {table} (works_id, {col}) VALUES (%s, %s)",  # noqa: S608
                    (wid, link_id),
                )

        for item in results:
            wid = int(item.get("id") or 0)
            if wid not in by_id or float(item.get("confidence") or 0) < min_confidence:
                continue
            scalar: dict[str, Any] = {}
            for field, column in (
                ("musical_key", "works_musical_key"), ("year", "works_year"),
                ("duration", "works_duration"), ("measures", "works_measures"),
                ("pages", "works_pages"), ("parts", "works_parts"),
                ("complexity", "works_complexity"), ("license", "works_license"),
                ("description", "works_description"), ("attribution_type", "works_attr_type"),
                ("attribution_note", "works_attribution_note"),
            ):
                value = item.get(field)
                if value not in (None, "", []):
                    scalar[column] = value
            if scalar:
                sets = ", ".join((f"{c} = %s" if overwrite else f"{c} = COALESCE({c}, %s)") for c in scalar)
                cur.execute(f"UPDATE works SET {sets} WHERE id = %s", (*scalar.values(), wid))  # noqa: S608
            names = lambda values: {_norm(v): genres[_norm(v)] for v in values if _norm(v) in genres}
            gids = list(names(item.get("genres") or []).values())
            eids = list(names(item.get("ensembles") or []).values()) if False else [ensembles[k] for k in (_norm(v) for v in item.get("ensembles") or []) if k in ensembles]
            iids = [instruments[k] for k in (_norm(v) for v in item.get("instruments") or []) if k in instruments]
            lids = [languages[str(v).lower()] for v in item.get("languages") or [] if str(v).lower() in languages]
            upsert_join("work_genres", "genres_id", wid, gids)
            upsert_join("work_ensembles", "ensembles_id", wid, eids)
            upsert_join("work_instruments", "instruments_id", wid, iids)
            upsert_join("work_language", "languages_id", wid, lids)
            log.append({"mode": "works", "id": wid, "applied": True, "confidence": item.get("confidence"),
                        "genres": gids, "ensembles": eids, "instruments": iids, "languages": lids})


def _providers(conn: pymysql.connections.Connection, db: str, limit: int, min_confidence: float, keys: list[str], *, apply: bool, list_only: bool, log: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT provider_id, name, kind, base_url, description FROM {db}.providers ORDER BY provider_id LIMIT %s", (limit,))
        rows = list(cur.fetchall())
    if list_only:
        for row in rows:
            print(row)
        return
    if not rows:
        print("proveedores: nada que revisar")
        return
    prompt = _PROMPT + json.dumps({"providers": rows}, ensure_ascii=False) + (
        "\nPara cada proveedor devuelve {id, confidence, description: {es,ca,fr,en,de}}; "
        "no repitas datos ya existentes."
    )
    data = _gemini({"contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}, keys)
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        print("proveedores: respuesta sin results")
        return
    for item in results:
        if not isinstance(item, dict) or float(item.get("confidence") or 0) < min_confidence:
            continue
        pid = str(item.get("id") or "")
        desc = item.get("description") or {}
        if not pid or not isinstance(desc, dict):
            continue
        log.append({"mode": "providers", "id": pid, "description": desc})
        if apply:
            with conn.cursor() as cur:
                cur.execute(f"SELECT description FROM {db}.providers WHERE provider_id=%s", (pid,))
                row = cur.fetchone()
                current = {}
                if row and row.get("description"):
                    try:
                        current = json.loads(row["description"])
                    except json.JSONDecodeError:
                        current = {}
                merged = {**current, **{k: v for k, v in desc.items() if v}}
                cur.execute(f"UPDATE {db}.providers SET description=%s WHERE provider_id=%s", (json.dumps(merged, ensure_ascii=False), pid))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("works", "providers", "all"), default="works")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--min-confidence", type=float, default=0.75)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--api-db", default="osap_api")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--list", action="store_true", help="solo lista candidatos, sin Gemini")
    args = ap.parse_args()
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    conf = _db_conf()
    _assert_dev(conf)
    conn = pymysql.connect(**conf, charset="utf8mb4", cursorclass=DictCursor)
    OUT.mkdir(exist_ok=True)
    log_path = OUT / f"ai_enrich_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    log: list[dict[str, Any]] = []
    try:
        if args.mode in {"works", "all"}:
            rows = _candidates(conn, args.limit)
            print(f"obras candidatas: {len(rows)}")
            if args.list:
                for row in rows:
                    print(row)
            elif rows:
                keys = _keys()
                for start in range(0, len(rows), args.batch):
                    chunk = rows[start:start + args.batch]
                    results = _ask_works(conn, chunk, keys)
                    _apply_works(conn, chunk, results, overwrite=args.overwrite,
                                 min_confidence=args.min_confidence, log=log)
                    print(f"  lote {start + 1}-{start + len(chunk)}: {len(results)} propuestas")
                if args.apply:
                    conn.commit()
        if args.mode in {"providers", "all"}:
            _providers(conn, args.api_db, args.limit, args.min_confidence, _keys(), apply=args.apply, list_only=args.list, log=log)
            if args.apply:
                conn.commit()
    finally:
        if log:
            log_path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in log), encoding="utf-8")
            print(f"auditoría: {log_path}")
        conn.close()
    if not args.apply:
        print("DRY-RUN: no se ha escrito nada (usa --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
