"""Revisión de personas con IA (Gemini) y aplicación de sus correcciones.

Dos fases:

1. GENERAR (`--generate`): envía lotes de nombres a Gemini con un esquema JSON estricto y
   guarda la respuesta en un fichero (`--out`). Campos por nombre: `is_person`, `action`
   (`keep|correct|merge|split|not_person|traditional`), `corrected_name`, `composers[]`,
   `birth_year`, `death_year`, `nationality`, `era`, `summary`, `confidence`.

2. APLICAR (`--apply`): lee la respuesta y actúa sobre `osap-storage`:
   - `keep`/`correct`  -> corrige `persons_name` (guardando el anterior como alias) y rellena
     años + ficha (`persons_biography_*`, `persons_birth_year/death_year`, `review_status`).
   - `merge`           -> fusiona en `corrected_name` (repunta y borra), con alias + historial.
   - `split`           -> crea/encuentra cada `composers[]` y liga la obra a TODOS (rol 1).
   - `traditional`     -> marca sus obras `works_attr_type='TRADICIONAL'` y desvincula la persona.
   - `not_person`      -> marca `works_attr_type='DESCONOCIDO'`, desvincula y oculta la persona.
   Reversible: backups + `persons_merge_history`.

Variables de entorno:
    GEMINI_API_KEY   (obligatoria para --generate)

Uso:
    set GEMINI_API_KEY=...
    .venv\\Scripts\\python.exe scripts/review_persons_ai.py --generate --names-file names.txt --out docs/ai/reviews.json
    .venv\\Scripts\\python.exe scripts/review_persons_ai.py --apply docs/ai/reviews.json
    .venv\\Scripts\\python.exe scripts/review_persons_ai.py --apply docs/ai/reviews.json --commit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

_MODEL = "gemini-flash-lite-latest"
_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "input": {"type": "string"},
                    "is_person": {"type": "boolean"},
                    "action": {"type": "string",
                               "enum": ["keep", "correct", "merge", "split", "not_person",
                                        "traditional"]},
                    "corrected_name": {"type": "string"},
                    "composers": {"type": "array", "items": {"type": "string"}},
                    "birth_year": {"type": "integer"},
                    "death_year": {"type": "integer"},
                    "nationality": {"type": "string"},
                    "era": {"type": "string"},
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["input", "is_person", "action", "confidence", "reason"],
            },
        }
    },
    "required": ["results"],
}
_INSTRUCTIONS = (
    "Eres un asistente de musicología. Para cada cadena, decide si es un compositor/persona "
    "real y devuelve el JSON del esquema. Acciones: keep (nombre ya correcto), correct "
    "(corrige el nombre en corrected_name), merge (es duplicado de otra persona -> "
    "corrected_name), split (varios compositores -> composers[]), not_person (no es persona: "
    "grupo/entidad/lugar/cosa), traditional (es obra/folk/danza/canción, no autor). Si es "
    "persona, rellena birth_year/death_year/nationality/era/summary (una frase). confidence 0..1. "
    "Nombres:\n"
)


def _db() -> dict:
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("db") or {}
    return {"host": conf.get("host", "127.0.0.1"), "port": int(conf.get("port", 3306)),
            "user": conf.get("user"), "password": conf.get("password"),
            "database": conf.get("name") or conf.get("database")}


_OR_URL = "https://openrouter.ai/api/v1/chat/completions"
_OR_MODEL_DEFAULT = "qwen/qwen3.8-27b:free"


def _keys(prefix: str = "GEMINI_API_KEY") -> list[str]:
    keys: list[str] = []
    for env in (prefix, f"{prefix}2", f"{prefix}S"):
        val = os.environ.get(env)
        if val:
            keys.extend(k.strip() for k in val.split(",") if k.strip())
    return keys


def _openrouter(names: list[str], keys: list[str], model: str) -> list[dict]:
    prompt = _INSTRUCTIONS + json.dumps(names, ensure_ascii=False)
    payload: dict = {"messages": [{"role": "user", "content": prompt}], "temperature": 0}
    last: Exception | None = None
    for attempt in range(max(6, len(keys) * 4)):
        key = keys[attempt % len(keys)]
        body = json.dumps({**payload, "model": model,
                           "response_format": {"type": "json_object"}}).encode()
        req = urllib.request.Request(_OR_URL, data=body, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode())
            text = data["choices"][0]["message"]["content"]
            return json.loads(text)["results"]
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503):
                time.sleep(min(30, 3 * (attempt + 1)))
                continue
            raise
    raise RuntimeError(f"OpenRouter no disponible tras reintentos: {last}")


def _gemini(names: list[str], keys: list[str]) -> list[dict]:
    body = json.dumps({
        "contents": [{"parts": [{"text": _INSTRUCTIONS + json.dumps(names, ensure_ascii=False)}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": _SCHEMA,
                             "temperature": 0},
    }).encode()
    last: Exception | None = None
    attempts = max(6, len(keys) * 4)
    for attempt in range(attempts):
        key = keys[attempt % len(keys)]
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:generateContent"
               f"?key={key}")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode())
            return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])["results"]
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 503):
                time.sleep(min(30, 3 * (attempt + 1)))
                continue
            raise
    raise RuntimeError(f"Gemini no disponible tras reintentos: {last}")


def generate(args: argparse.Namespace) -> int:
    if args.provider == "openrouter":
        keys = _keys("OPENROUTER_API_KEY")
        caller = lambda chunk: _openrouter(chunk, keys, args.model or _OR_MODEL_DEFAULT)  # noqa: E731
    else:
        keys = _keys("GEMINI_API_KEY")
        caller = lambda chunk: _gemini(chunk, keys)  # noqa: E731
    if not keys:
        print(f"error: falta la clave de {args.provider}")
        return 2
    names = [ln.strip() for ln in Path(args.names_file).read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    out: list[dict] = []
    out_path = Path(args.out)
    if out_path.exists():
        out = json.loads(out_path.read_text(encoding="utf-8"))
        done = {r["input"] for r in out}
        names = [n for n in names if n not in done]
        print(f"reanudando: {len(done)} ya hechas, {len(names)} pendientes")
    if args.limit:
        names = names[: args.limit]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(names), args.batch):
        chunk = names[i: i + args.batch]
        out.extend(caller(chunk))
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {i + len(chunk)}/{len(names)} (total {len(out)})")
    print(f"escrito {args.out} ({len(out)} revisiones)")
    return 0


# ---------------------------------------------------------------- apply
def _repoint(cur, keeper: str, dup: str) -> None:
    for tbl, col in (("works_person_roles", "works_person_roles_person_id"),
                     ("persons_aliases", "person_id"), ("persons_identity", "persons_id"),
                     ("persons_evidence", "persons_id"), ("cpdl_edition_persons", "persons_id"),
                     ("representation_persons", "representation_persons_person_id")):
        cur.execute(f"UPDATE IGNORE {tbl} SET {col}=%s WHERE {col}=%s", (keeper, dup))
        cur.execute(f"DELETE FROM {tbl} WHERE {col}=%s", (dup,))


def _alias(cur, pid: str, name: str) -> None:
    cur.execute("INSERT IGNORE INTO persons_aliases (person_id, person_aliases_alias, "
                "person_aliases_normalized_alias, person_aliases_name_type, person_aliases_source) "
                "VALUES (%s,%s,%s,'variant_ai','ai')", (pid, name, name.strip().lower()))


def _bio(cur, pid: str, r: dict) -> None:
    cur.execute(
        "UPDATE persons SET persons_birth_year=%s, persons_death_year=%s, "
        "persons_biography_summary=%s, persons_biography_era=%s, persons_biography_nationality=%s, "
        "persons_review_status='reviewed', persons_reviewed_at=NOW(6), persons_visible=1, "
        "persons_updated_at=NOW(6) WHERE persons_id=%s",
        (str(r["birth_year"]) if r.get("birth_year") else None,
         str(r["death_year"]) if r.get("death_year") else None,
         r.get("summary") or None, r.get("era") or None, r.get("nationality") or None, pid))


def apply(args: argparse.Namespace) -> int:
    reviews = json.loads(Path(args.apply_file).read_text(encoding="utf-8"))
    conn = pymysql.connect(**_db(), charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        for r in reviews:
            if float(r.get("confidence") or 0) < args.min_confidence:
                print(f"  baja confianza ({r.get('confidence')}): {r['input']!r}")
                continue
            cur.execute("SELECT persons_id FROM persons WHERE persons_name=%s LIMIT 1", (r["input"],))
            row = cur.fetchone()
            pid = row["persons_id"] if row else None
            action = r["action"]
            print(f"  [{action}] {r['input']!r} -> {r.get('corrected_name') or r.get('composers') or ''}")
            if not args.commit:
                continue
            if action in ("keep", "correct"):
                if pid is None:
                    continue
                target = pid
                if action == "correct" and r.get("corrected_name"):
                    cur.execute("SELECT persons_id FROM persons WHERE persons_name=%s LIMIT 1",
                                (r["corrected_name"],))
                    tgt = cur.fetchone()
                    if tgt and tgt["persons_id"] != pid:
                        # El nombre destino ya existe -> fusiona (no crea duplicado).
                        _repoint(cur, tgt["persons_id"], pid)
                        _alias(cur, tgt["persons_id"], r["input"])
                        cur.execute("INSERT INTO persons_merge_history (source_person_id, "
                                    "target_person_id, merged_by) "
                                    "VALUES (%s,%s,'review_persons_ai')", (pid, tgt["persons_id"]))
                        cur.execute("DELETE FROM persons WHERE persons_id=%s", (pid,))
                        target = tgt["persons_id"]
                    else:
                        cur.execute("UPDATE persons SET persons_name=%s, persons_updated_at=NOW(6) "
                                    "WHERE persons_id=%s", (r["corrected_name"], pid))
                        _alias(cur, pid, r["input"])
                _bio(cur, target, r)
            elif action == "merge":
                if not pid or not r.get("corrected_name"):
                    continue
                cur.execute("SELECT persons_id FROM persons WHERE persons_name=%s LIMIT 1",
                            (r["corrected_name"],))
                tgt = cur.fetchone()
                if tgt and tgt["persons_id"] != pid:
                    _repoint(cur, tgt["persons_id"], pid)
                    _alias(cur, tgt["persons_id"], r["input"])
                    cur.execute("INSERT INTO persons_merge_history (source_person_id, target_person_id, "
                                "merged_by) VALUES (%s,%s,'review_persons_ai')", (pid, tgt["persons_id"]))
                    cur.execute("DELETE FROM persons WHERE persons_id=%s", (pid,))
            elif action == "split":
                if not pid or not r.get("composers"):
                    continue
                cur.execute("SELECT DISTINCT works_person_roles_work_id wid FROM works_person_roles "
                            "WHERE works_person_roles_person_id=%s AND works_person_roles_role_id=1",
                            (pid,))
                works = [w["wid"] for w in cur.fetchall()]
                markers = {"tradicional", "traditional", "anon", "anónimo", "anonimo", "anonymous",
                           "desconocido", "unknown", "folk", "trad"}
                real = [c for c in r["composers"] if str(c).strip().lower() not in markers]
                if len(real) != len(r["composers"]) and works:  # token no-persona -> tradicional
                    cur.execute("UPDATE works SET works_attr_type='TRADICIONAL' WHERE id IN ("
                                + ",".join(["%s"] * len(works)) + ")", works)
                for idx, name in enumerate(real, 1):
                    cur.execute("SELECT persons_id FROM persons WHERE persons_name=%s LIMIT 1", (name,))
                    t = cur.fetchone()
                    np = t["persons_id"] if t else str(uuid.uuid4())
                    if not t:
                        cur.execute("INSERT INTO persons (persons_id, persons_name, "
                                    "persons_source_system, persons_visible, persons_created_at, "
                                    "persons_updated_at) VALUES (%s,%s,'ai',1,NOW(6),NOW(6))",
                                    (np, name))
                    for wid in works:
                        cur.execute("INSERT IGNORE INTO works_person_roles "
                                    "(works_person_roles_work_id, works_person_roles_person_id, "
                                    "works_person_roles_role_id, works_person_roles_order) "
                                    "VALUES (%s,%s,1,%s)", (wid, np, idx))
                cur.execute("DELETE FROM works_person_roles WHERE works_person_roles_person_id=%s", (pid,))
                cur.execute("DELETE FROM persons WHERE persons_id=%s", (pid,))
            elif action in ("traditional", "not_person"):
                if not pid:
                    continue
                attr = "TRADICIONAL" if action == "traditional" else "DESCONOCIDO"
                cur.execute("SELECT DISTINCT works_person_roles_work_id wid FROM works_person_roles "
                            "WHERE works_person_roles_person_id=%s AND works_person_roles_role_id=1",
                            (pid,))
                ws = [w["wid"] for w in cur.fetchall()]
                if ws:
                    cur.execute("UPDATE works SET works_attr_type=%s WHERE id IN ("
                                + ",".join(["%s"] * len(ws)) + ")", [attr, *ws])
                cur.execute("DELETE FROM works_person_roles WHERE works_person_roles_person_id=%s "
                            "AND works_person_roles_role_id=1", (pid,))
                cur.execute("UPDATE persons SET persons_visible=0, persons_review_status='reviewed', "
                            "persons_review_reason=%s WHERE persons_id=%s", (action, pid))
    if args.commit:
        conn.commit()
    else:
        print("DRY-RUN: usa --commit para escribir")
    conn.close()
    return 0


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--provider", choices=("gemini", "openrouter"), default="gemini")
    ap.add_argument("--model", default=None, help="modelo (por defecto: lite de Gemini o llama free)")
    ap.add_argument("--apply", dest="apply_file", default=None, metavar="JSON")
    ap.add_argument("--names-file", default=None)
    ap.add_argument("--out", default="docs/ai/reviews_persons.json")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-confidence", type=float, default=0.8)
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    if args.generate:
        if not args.names_file:
            print("error: --generate requiere --names-file")
            return 2
        return generate(args)
    if args.apply_file:
        return apply(args)
    print("nada que hacer: usa --generate o --apply")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
