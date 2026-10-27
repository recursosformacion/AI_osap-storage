"""Valida propuestas de limpieza de nombres con Gemini y opcionalmente las aplica.

Lee data/person_name_cleanup/proposals.json. Para cada candidato pide a Gemini que decida
si el nombre contaminado corresponde a un compositor real y devuelve un JSON. No inventa:
si no hay evidencia, action=keep/reject.

Uso:
    .venv\\Scripts\\python.exe scripts/validate_cleanup_ai.py
    .venv\\Scripts\\python.exe scripts/validate_cleanup_ai.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pymysql
import yaml

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "data" / "person_name_cleanup" / "proposals.json"
OUT_PATH = ROOT / "data" / "person_name_cleanup" / "ai_validation.json"
SECRETS = [ROOT / "secrets" / "gemini.prod.key", ROOT / "secrets" / "gemini.key"]
MODEL = "gemini-flash-lite-latest"
try:
    import certifi

    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = None


def _keys() -> list[str]:
    keys: list[str] = []
    for path in SECRETS:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                value = line.split("=", 1)[-1].strip()
                if value and value not in keys:
                    keys.append(value)
    return keys


def _call(prompt: str, key: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={urllib.parse.quote(key)}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120, context=_SSL) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["candidates"][0]["content"]["parts"][0]["text"]


def _parse(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\[[\s\S]*\]", text)
    return json.loads(match.group(0) if match else text)


def _db():
    conf = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {})["db"]
    return pymysql.connect(
        host=conf["host"],
        port=conf["port"],
        user=conf["user"],
        password=conf["password"],
        database=conf["name"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _existing(cur, name: str) -> str | None:
    cur.execute("SELECT persons_id FROM persons WHERE LOWER(TRIM(persons_name))=LOWER(TRIM(%s)) LIMIT 1", (name,))
    row = cur.fetchone()
    return row["persons_id"] if row else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-confidence", type=float, default=0.85)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--use-existing", action="store_true")
    args = ap.parse_args()
    keys = _keys()
    if not keys:
        raise SystemExit("No hay clave Gemini en secrets/")
    proposals = json.loads(IN_PATH.read_text(encoding="utf-8"))
    decisions = (
        json.loads(OUT_PATH.read_text(encoding="utf-8"))
        if args.use_existing and OUT_PATH.exists()
        else []
    )
    selected = [
        p
        for p in proposals
        if p.get("kind") in {"composer_name", "composer_from_work_title"} and p.get("candidate_name")
    ]
    for start in range(0, len(selected), args.batch):
        if decisions:
            break
        chunk = selected[start : start + args.batch]
        items = [
            {
                "persons_id": p["persons_id"],
                "original_name": p["persons_name"],
                "candidate_composer": p["candidate_name"],
                "work_titles": (p.get("works") or [])[:3],
                "kind": p.get("kind"),
            }
            for p in chunk
        ]
        prompt = (
            "Eres musicólogo y bibliotecario. Valida estos registros de personas. "
            "El nombre original puede contener una obra, un compositor, un arreglista, una URL "
            "o un crédito de MuseScore/hymnary. Decide el compositor real solo si hay evidencia. "
            "No inventes nombres. Devuelve un array JSON con exactamente estos campos: "
            "persons_id, composer (string o null), confidence (0-1), action "
            "(rename|keep|reject), reason. Usa rename solo si el candidato o el título de la obra "
            "identifican de forma clara a un compositor humano. Los himnarios pueden indicar el "
            "compositor de la melodía; no confundas el título de la obra con el compositor.\n"
            + json.dumps(items, ensure_ascii=False)
        )
        last: Exception | None = None
        for attempt in range(3):
            key = keys[(start // max(args.batch, 1) + attempt) % len(keys)]
            try:
                decisions.extend(_parse(_call(prompt, key)))
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(2 + attempt * 2)
        else:
            raise RuntimeError(f"Gemini falló en lote {start}: {last}")
        print(f"lote {start}/{len(selected)}", flush=True)
    OUT_PATH.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    by_id = {str(d.get("persons_id")): d for d in decisions}
    applied = skipped = conflicts = 0
    if args.apply:
        conn = _db()
        try:
            with conn.cursor() as cur:
                for p in selected:
                    d = by_id.get(str(p["persons_id"])) or {}
                    composer = str(d.get("composer") or "").strip()
                    confidence = float(d.get("confidence") or 0)
                    if d.get("action") != "rename" or not composer or confidence < args.min_confidence:
                        skipped += 1
                        continue
                    if "&" in composer or " and " in composer.casefold() or ";" in composer:
                        skipped += 1
                        continue
                    existing = _existing(cur, composer)
                    if existing and existing != p["persons_id"]:
                        conflicts += 1
                        continue
                    if existing == p["persons_id"]:
                        skipped += 1
                        continue
                    cur.execute(
                        "UPDATE persons SET persons_name=%s, persons_updated_at=NOW(6) WHERE persons_id=%s",
                        (composer, p["persons_id"]),
                    )
                    applied += 1
            conn.commit()
        finally:
            conn.close()
    print(
        f"decisiones={len(decisions)} seleccionados={len(selected)} "
        f"aplicados={applied} omitidos={skipped} conflictos={conflicts}"
    )
    print(f"json={OUT_PATH}")
    print("BD actualizada" if args.apply else "DRY-RUN: no se ha escrito en la BD")
    return 0


if __name__ == "__main__":
    sys.exit(main())




