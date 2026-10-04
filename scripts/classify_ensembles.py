"""Clasifica los `ensembles` de osap-storage (READ-ONLY) para planificar la limpieza.

Objetivo: separar notación vocal válida (SATB, AATTB…), nombres descriptivos, posibles
artefactos (letras sueltas, símbolos, corruptos) y duplicados normalizables. **No escribe
nada** y **no elimina nada**: solo informa para construir después el mapa origen→destino.

Uso:
    PYTHONPATH=. .venv/bin/python -m scripts.classify_ensembles [--out output/ensembles_classification.json]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from infrastructure.config import Settings
from infrastructure.db.connection import Database

# S,A,T,B = cuerdas; M = mixto; C = niños; R = barítono (SATBARB…).
_VOCAL_RE = re.compile(r"^[SATBMCR]{2,16}$")
_LETTER_RE = re.compile(r"^[A-Z]{1,16}$")
_HTML_ENTITY_RE = re.compile(r"&[A-Za-z]+;?")
_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑ]{3,}")
# símbolos no musicales (entidades HTML sin decodificar, almohadillas, barras…)
_SYMBOL_RE = re.compile(r"[&<>#|{}\[\]\\^~`\u0000-\u001f]")


def normalize(code: str) -> str:
    """Forma canónica para detectar duplicados.

    Mayúsculas; se eliminan espacios/guiones/underscores (variantes de formato dentro de
    la MISMA formación, p. ej. `SA T B` -> `SATB`). Se **preservan los puntos**, que
    distinguen multi-coro (`SATB.SATB` ≠ `SATB`) para no sobre-fusionar.
    """
    base = unicodedata.normalize("NFKC", code).strip().upper()
    base = re.sub(r"[^A-Z0-9.]", "", base)
    return re.sub(r"\.+", ".", base).strip(".")


def classify(code: str, name: str) -> str:
    raw = unicodedata.normalize("NFKC", code).strip()
    if not raw:
        return "empty"
    if "\ufffd" in raw or any(unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs") for ch in raw):
        return "corrupt"
    decoded = html.unescape(raw)
    norm = normalize(decoded)
    if not norm:
        return "artifact_symbol"
    # Notación vocal: solo letras del conjunto de voces y ≥2 distintas (SATB, AATTB, SATB.SATB, SATBARB…).
    if _VOCAL_RE.fullmatch(norm) and len(set(norm)) >= 2:
        return "vocal_notation"
    # Letra única repetida (A, AA, S, SS, TTT…): fragmento, no formación completa.
    if _LETTER_RE.fullmatch(norm) and len(set(norm)) == 1:
        return "artifact_letter"
    # Descripción textual: contiene alguna palabra de ≥3 letras (SOLO SOPRANO, UNISON, A CAPP, EQUAL VOICES…).
    if _WORD_RE.search(decoded):
        if "&" in raw and _HTML_ENTITY_RE.search(raw):
            return "html_entity"  # descripción con entidad HTML sin decodificar
        return "descriptive"
    if _SYMBOL_RE.search(decoded) or _HTML_ENTITY_RE.search(raw):
        return "artifact_symbol"
    return "other"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output/ensembles_classification.json")
    args = parser.parse_args()

    settings = Settings()  # type: ignore[call-arg]
    db = Database(settings)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT e.id, e.ensembles_code AS code, e.ensembles_name AS name, "
            "COALESCE(e.ensembles_description,'') AS description, "
            "(SELECT COUNT(*) FROM work_ensembles we WHERE we.ensembles_id = e.id) AS works "
            "FROM ensembles e"
        )
        rows = [dict(r) for r in await cur.fetchall()]

    categorias: dict[str, list[dict]] = defaultdict(list)
    por_norm: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        r["works"] = int(r.get("works") or 0)
        r["norm"] = normalize(str(r.get("code") or r.get("name") or ""))
        categorias[classify(str(r.get("code") or ""), str(r.get("name") or ""))].append(r)
        por_norm[r["norm"]].append(r)

    dup_groups = {k: v for k, v in por_norm.items() if len(v) > 1 and k}
    dup_ids = {r["id"] for v in dup_groups.values() for r in v}

    resumen = {k: len(v) for k, v in sorted(categorias.items(), key=lambda kv: -len(kv[1]))}
    informe = {
        "total": len(rows),
        "resumen": resumen,
        "duplicados_grupos": len(dup_groups),
        "duplicados_elementos": len(dup_ids),
        "muestras": {
            k: [{"id": r["id"], "code": r["code"], "name": r["name"], "works": r["works"]}
                for r in sorted(v, key=lambda x: -x["works"])[:15]]
            for k, v in categorias.items()
        },
        "duplicados": [
            {"norm": k, "elementos": [
                {"id": r["id"], "code": r["code"], "name": r["name"], "works": r["works"]}
                for r in sorted(v, key=lambda x: -x["works"])
            ]}
            for k, v in sorted(dup_groups.items(), key=lambda kv: -len(kv[1]))[:60]
        ],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"total": informe["total"], "resumen": resumen,
                      "duplicados_grupos": informe["duplicados_grupos"],
                      "duplicados_elementos": informe["duplicados_elementos"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
