"""Pipeline de obras: crea lotes JSON enriquecidos, los envía a Gemini y guarda respuestas.

Igual que el pipeline de personas:
- `--build-only`: solo genera `data/works_ai_in/json_works_lote_NNNNN.json` desde la BD local.
- sin `--build-only`: además envía cada lote (20 obras) a Gemini y guarda
  `data/works_ai_out/json_works_lote_NNNNN.json`.
- Reanudable: salta lotes ya generados/enviados.
- Solo lee la BD. La aplicación la hace `apply_works_ai_json.py`.

Uso:
    .venv\\Scripts\\python.exe scripts/works_ai_runner.py --build-only --limit 2
    .venv\\Scripts\\python.exe scripts/works_ai_runner.py --start 1 --limit 5
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
from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_IN = DATA / "works_ai_in"
OUT_OUT = DATA / "works_ai_out"
PROMPT = (ROOT / "scripts" / "works_ai_prompt.txt").read_text(encoding="utf-8")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
API = "https://generativelanguage.googleapis.com/v1beta/models"
RETRY = {429, 500, 502, 503, 504}
BATCH = 20


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
    return pymysql.connect(host=host, port=port, user=conf.get("user"), password=conf.get("password"),
                           database=conf.get("name"), charset="utf8mb4", cursorclass=DictCursor)


def _allowed(conn: pymysql.connections.Connection) -> dict[str, list[str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM genres ORDER BY name")
        genres = [r["name"] for r in cur.fetchall()]
        cur.execute("SELECT ensembles_name FROM ensembles ORDER BY ensembles_name")
        ensembles = [r["ensembles_name"] for r in cur.fetchall()]
        cur.execute("SELECT name_en FROM instruments ORDER BY name_en")
        instruments = [r["name_en"] for r in cur.fetchall()]
        cur.execute("SELECT languages_code FROM languages ORDER BY languages_code")
        languages = [r["languages_code"] for r in cur.fetchall()]
    return {"genres": genres[:400], "ensembles": ensembles[:400],
            "instruments": instruments[:400], "languages": languages[:400]}


def _batch(conn: pymysql.connections.Connection, offset: int) -> list[dict[str, Any]]:
    sql = """
        SELECT w.id AS works_id, w.works_title AS title, w.works_subtitle AS subtitle,
               w.works_catalogue AS catalogue, w.works_opus AS opus,
               w.works_attr_type AS attr_type, w.works_attribution_note AS attribution_note,
               w.works_year AS year, w.works_year_from AS year_from, w.works_year_to AS year_to,
               w.works_musical_key AS musical_key, w.works_duration AS duration,
               w.works_measures AS measures, w.works_pages AS pages, w.works_parts AS parts,
               w.works_complexity AS complexity, w.works_license AS license,
               w.works_description AS description, w.works_instrumentation AS instrumentation,
               w.works_source_url AS works_source_url,
               (SELECT GROUP_CONCAT(DISTINCT p.persons_name ORDER BY p.persons_name SEPARATOR '; ')
                  FROM works_person_roles r JOIN persons p ON p.persons_id = r.works_person_roles_person_id
                 WHERE r.works_person_roles_work_id = w.id AND r.works_person_roles_role_id = 1) AS composers,
               (SELECT GROUP_CONCAT(DISTINCT g.name ORDER BY g.name SEPARATOR '; ')
                  FROM work_genres wg JOIN genres g ON g.id = wg.genres_id WHERE wg.works_id = w.id) AS genres,
               (SELECT GROUP_CONCAT(DISTINCT e.ensembles_name ORDER BY e.ensembles_name SEPARATOR '; ')
                  FROM work_ensembles we JOIN ensembles e ON e.id = we.ensembles_id WHERE we.works_id = w.id) AS ensembles,
               (SELECT GROUP_CONCAT(DISTINCT i.name_en ORDER BY i.name_en SEPARATOR '; ')
                  FROM work_instruments wi JOIN instruments i ON i.id = wi.instruments_id WHERE wi.works_id = w.id) AS instruments,
               (SELECT GROUP_CONCAT(DISTINCT l.languages_code ORDER BY l.languages_code SEPARATOR '; ')
                  FROM work_language wl JOIN languages l ON l.id = wl.languages_id WHERE wl.works_id = w.id) AS languages
        FROM works w
        ORDER BY w.id
        LIMIT %s OFFSET %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (BATCH, offset))
        rows = list(cur.fetchall())
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in row.items():
            if key in {"composers", "genres", "ensembles", "instruments", "languages"}:
                item[key] = [x for x in str(value or "").split("; ") if x]
            else:
                item[key] = value
        out.append(item)
    return out


def _call(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    last = ""
    for attempt in range(max(1, len(keys) * 3)):
        key = keys[attempt % len(keys)]
        try:
            req = urllib.request.Request(
                f"{API}/{MODEL}:generateContent?key={key}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
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
            last = f"HTTP {exc.code}"
            if exc.code == 400:
                continue
            if exc.code not in RETRY:
                raise
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"Gemini no disponible: {last}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    keys = _keys()
    if not args.build_only and not keys:
        print("ERROR: faltan GEMINI_API_KEY / GEMINI_API_KEY2", file=sys.stderr)
        return 2
    OUT_IN.mkdir(parents=True, exist_ok=True)
    OUT_OUT.mkdir(parents=True, exist_ok=True)
    conn = _db()
    allowed = _allowed(conn)
    done = 0
    try:
        n = args.start
        while True:
            if args.limit and done >= args.limit:
                break
            offset = (n - 1) * BATCH
            src = OUT_IN / f"json_works_lote_{n:05d}.json"
            dst = OUT_OUT / f"json_works_lote_{n:05d}.json"
            if dst.exists() and not args.force:
                n += 1
                continue
            if not src.exists() or args.force:
                rows = _batch(conn, offset)
                if not rows:
                    break
                src.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  lote {n:05d}: {len(rows)} obras -> {src.name}")
                if args.build_only:
                    done += 1
                    n += 1
                    continue
            rows = json.loads(src.read_text(encoding="utf-8"))
            payload = {
                "contents": [{"parts": [{"text": PROMPT + "\n\nLISTAS PERMITIDAS:\n" +
                    json.dumps(allowed, ensure_ascii=False) + "\n\nLOTE:\n" +
                    json.dumps(rows, ensure_ascii=False)}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
            }
            result = _call(payload, keys)
            dst.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  lote {n:05d}: {len(result)} respuestas -> {dst.name}")
            done += 1
            n += 1
            time.sleep(max(0.0, args.sleep))
    finally:
        conn.close()
    print(f"lotes procesados: {done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
