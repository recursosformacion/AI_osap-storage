"""Genera lotes enriquecidos de personas y los envía a Gemini, guardando la respuesta JSON.

- Lee `data/json_personas_lote_NNN.json` (entrada).
- Añade a cada persona hasta 5 títulos de obras (`works`) desde la BD local.
- Envía el lote (20) con `scripts/persons_ai_prompt.txt` a Gemini.
- Guarda `data/ai_out/json_personas_lote_NNN.json` y es reanudable.

Solo lee la BD. No escribe en `persons`: la incorporación la hace
`apply_persons_ai_json.py`.

Uso:
    .venv\\Scripts\\python.exe scripts/persons_ai_runner.py --dry-run --start 6 --limit 1
    .venv\\Scripts\\python.exe scripts/persons_ai_runner.py --start 6
    .venv\\Scripts\\python.exe scripts/persons_ai_runner.py --start 6 --limit 20 --sleep 1.5
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "ai_out"
PROMPT = (ROOT / "scripts" / "persons_ai_prompt.txt").read_text(encoding="utf-8")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
API = "https://generativelanguage.googleapis.com/v1beta/models"
RETRY = {429, 500, 502, 503, 504}


def _retry_delay(attempt: int, headers: Any, error: dict[str, Any]) -> float:
    retry_after = headers.get("Retry-After") if headers else None
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass

    for detail in error.get("details", []):
        retry_delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(retry_delay or ""))
        if match:
            return float(match.group(1))
    return min(2**attempt, 10)


def _keys() -> list[str]:
    keys: list[str] = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEY2", "GEMINI_API_KEYS"):
        value = os.environ.get(name, "")
        if value:
            keys.extend(p for p in re.split(r"[,;\s]+", value) if p)
    return list(dict.fromkeys(keys))


def _db() -> pymysql.connections.Connection:
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("db") or {}
    host = conf.get("host", "127.0.0.1")
    port = int(conf.get("port", 3306))
    if host not in {"127.0.0.1", "localhost"} or port == 3307:
        raise SystemExit("rechazado: solo BD local de desarrollo")
    return pymysql.connect(
        host=host, port=port, user=conf.get("user"), password=conf.get("password"),
        database=conf.get("name"), charset="utf8mb4", cursorclass=DictCursor,
    )


def _works(conn: pymysql.connections.Connection, person_ids: list[str]) -> dict[str, list[str]]:
    if not person_ids:
        return {}
    placeholders = ",".join(["%s"] * len(person_ids))
    sql = f"""
        SELECT r.works_person_roles_person_id AS pid, w.works_title AS title
        FROM works_person_roles r
        JOIN works w ON w.id = r.works_person_roles_work_id
        WHERE r.works_person_roles_person_id IN ({placeholders})
          AND r.works_person_roles_role_id = 1
        ORDER BY r.works_person_roles_person_id, w.works_year IS NULL, w.works_year, w.id
    """
    out: dict[str, list[str]] = {pid: [] for pid in person_ids}
    with conn.cursor() as cur:
        cur.execute(sql, person_ids)
        for row in cur.fetchall():
            pid = str(row["pid"])
            if len(out.get(pid, [])) < 5:
                out.setdefault(pid, []).append(str(row["title"]))
    return out


def _enrich(conn: pymysql.connections.Connection, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [str(r.get("persons_id")) for r in batch if r.get("persons_id")]
    works = _works(conn, ids)
    for row in batch:
        row["works"] = works.get(str(row.get("persons_id")), [])
    return batch


def _call(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    last: str = ""
    for attempt in range(max(1, len(keys) * 3)):
        key = keys[attempt % len(keys)]
        delay = min(2**attempt, 10)
        try:
            req = urllib.request.Request(
                f"{API}/{MODEL}:generateContent?key={key}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
                parsed = parsed["results"]
            if not isinstance(parsed, list):
                raise RuntimeError("respuesta sin array JSON")
            return [x for x in parsed if isinstance(x, dict)]
        except urllib.error.HTTPError as exc:
            try:
                error_data = json.loads(exc.read())
            except (UnicodeDecodeError, json.JSONDecodeError):
                error_data = {}
            error = error_data.get("error", {}) if isinstance(error_data, dict) else {}
            message = error.get("message", "") if isinstance(error, dict) else ""
            last = f"HTTP {exc.code}" + (f": {message}" if message else "")
            if exc.code == 400:
                continue
            if exc.code not in RETRY:
                raise
            delay = _retry_delay(attempt, exc.headers, error)
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(delay)
    raise RuntimeError(f"Gemini no disponible: {last}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    keys = _keys()
    if not args.dry_run and not keys:
        print("ERROR: faltan GEMINI_API_KEY / GEMINI_API_KEY2", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    conn = _db()
    done = 0
    try:
        n = args.start
        while True:
            if args.limit and done >= args.limit:
                break
            src = DATA / f"json_personas_lote_{n:03d}.json"
            if not src.exists():
                if n > args.start + 3000:
                    break
                n += 1
                continue
            dst = args.out_dir / src.name
            if dst.exists() and not args.force:
                print(f"  {n:03d}: ya existe, se omite")
                n += 1
                continue
            batch = json.loads(src.read_text(encoding="utf-8"))
            if not isinstance(batch, list) or not batch:
                print(f"  {n:03d}: lote vacío/erróneo, se omite")
                n += 1
                continue
            batch = _enrich(conn, batch)
            if args.dry_run:
                print(f"  {n:03d}: {len(batch)} registros; works ejemplo={batch[0].get('works')}")
                done += 1
                n += 1
                continue
            payload = {
                "contents": [{"parts": [{"text": PROMPT + "\n\nLOTE:\n" + json.dumps(batch, ensure_ascii=False)}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
            }
            result = _call(payload, keys)
            # Preserva `works` aunque el modelo lo omita.
            by_id = {str(r.get("persons_id")): r for r in batch}
            for row in result:
                pid = str(row.get("persons_id"))
                if pid in by_id and "works" not in row:
                    row["works"] = by_id[pid].get("works", [])
            dst.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            with (args.out_dir / "progress.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"batch": n, "rows": len(result), "at": time.time()}) + "\n")
            print(f"  {n:03d}: {len(result)} respuestas -> {dst.name}")
            done += 1
            n += 1
            time.sleep(max(0.0, args.sleep))
    finally:
        conn.close()
    print(f"lotes procesados: {done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
