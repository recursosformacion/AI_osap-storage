"""Mapea el género de las páginas CPDL a los 12 géneros de `genres` y puebla `work_genres`.

El corpus CPDL (G:\\cpdl_chunks) usa la taxonomía coral de ChoralWiki (776 valores:
Sacred, Motets, Madrigals, Partsongs…). Aquí se reduce a nuestros 12 géneros con reglas
explícitas + palabras clave. El mapeo se guarda en `genre_mappings` con prefijo `cpdl:`
(para poder revisarlo/ajustarlo) y las relaciones en `work_genres`.

Uso:
    .venv\\Scripts\\python.exe scripts/map_cpdl_genres.py --dry-run
    .venv\\Scripts\\python.exe scripts/map_cpdl_genres.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

_spec = importlib.util.spec_from_file_location("icw", ROOT / "scripts" / "import_cpdl_works.py")
_icw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_icw)

C = {
    "clasica": 1,
    "sacra": 2,
    "folk": 3,
    "escenica": 12,
}

# Valores frecuentes con criterio fijo (el resto cae en reglas por palabra clave).
_EXPLICIT: dict[str, int] = {}
for _v in (
    "sacred", "motets", "hymns", "anthems", "masses", "carols", "chorales",
    "evening canticles", "antiphons", "responsories", "cantatas", "sacred songs",
    "liturgical music", "eucharistic songs", "communions", "chants", "introits",
    "office hymns", "anglican chants", "psalm-tunes", "vesper psalms", "offertories",
    "votive antiphons", "descants", "vespers", "morning canticles", "magnificat antiphons",
    "mass propers", "verse anthems", "hymn settings", "sequence hymns", "laude", "graduals",
    "requiems", "lamentations", "tenebrae responsories", "spirituals", "gospel motets",
    "oratorios", "communion services", "responsorial psalms", "mass fragments",
    "preces and responses", "alleluia verses", "passions", "litanies", "vernacular masses",
    "hymn tunes", "burial services", "christmas", "folk hymns", "sacred laments",
    "troped kyries", "tenebrae music", "psalms", "tracts", "te deum",
):
    _EXPLICIT[_v] = C["sacra"]
for _v in (
    "secular", "madrigals", "partsongs", "chansons", "glees", "canons", "villanellas",
    "canzonette", "art songs", "lute songs", "canzoni", "frottole", "consort songs",
    "odes", "rondeaux", "ballades", "barbershops", "humorous songs", "children's songs",
    "instrumental music", "symphonies", "romances", "ballate", "set pieces",
):
    _EXPLICIT[_v] = C["clasica"]
for _v in ("folksongs", "villancicos", "christmas (secular)", "nursery rhymes",
           "lullabies", "patriotic music", "pagan music"):
    _EXPLICIT[_v] = C["folk"]
for _v in ("arias", "operas", "operettas"):
    _EXPLICIT[_v] = C["escenica"]

# Reglas por palabra clave, en orden (primera coincidencia gana).
_RULES: list[tuple[int, tuple[str, ...]]] = [
    (C["sacra"], ("sacred", "motet", "mass", "hymn", "anthem", "canticle", "antiphon",
                  "responsor", "liturg", "eucharist", "communion", "introit", "psalm",
                  "vesper", "offertor", "descant", "requiem", "lament", "tenebrae",
                  "passion", "laude", "gradual", "chant", "spiritual", "litany", "benedic",
                  "magnificat", "preces", "alleluia", "tract", "votive", "anglican",
                  "sanctus", "kyrie", "gospel", "burial", "funeral", "carol", "chorale",
                  "oratorio", "christmas", "te deum")),
    (C["folk"], ("folk", "villancico", "traditional", "nursery", "lullab", "ballad",
                 "country", "patriotic", "pagan")),
    (C["escenica"], ("opera", "operetta", "aria", "stage", "incidental", "zarzuela",
                     "ballet", "musical")),
]

_SKIP = {"", "unknown", "other", "unspecified", "dual", "both", "none", "n/a"}
_DEFAULT = C["clasica"]


def genre_of(value: str) -> int | None:
    """Género (1-12) para un valor de CPDL, o None si es ruido."""
    v = (value or "").strip().lower()
    if not v or "=" in v or v in _SKIP:
        return None
    if v in _EXPLICIT:
        return _EXPLICIT[v]
    for gid, keys in _RULES:
        if any(k in v for k in keys):
            return gid
    return _DEFAULT


def _pages(paths: list[Path]):
    for path in paths:
        for _event, elem in ElementTree.iterparse(path, events=("end",)):
            if elem.tag != _icw.NS + "page":
                continue
            title = (elem.findtext(_icw.NS + "title") or "").strip()
            pid = elem.findtext(_icw.NS + "id") or ""
            text = elem.findtext(".//" + _icw.NS + "text") or ""
            elem.clear()
            if pid.isdigit() and _icw._looks_like_work(text):
                yield int(pid), title, text


async def run(paths: list[Path], db_name: str, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    page_genres: dict[int, set[int]] = {}
    value_hits: Counter = Counter()
    mapped = skipped = 0
    distinct: dict[str, int] = {}
    for pid, _title, text in _pages(paths):
        rec = _icw._parse_page(pid, _title, text)
        gids: set[int] = set()
        for raw in rec["genre"]:
            gid = genre_of(raw)
            if gid is None:
                skipped += 1
                continue
            gids.add(gid)
            value_hits[raw.strip().lower()] += 1
        if gids:
            page_genres[pid] = gids
            mapped += 1
        for raw in rec["genre"]:
            distinct[raw.strip().lower()] = distinct.get(raw.strip().lower(), 0) + 1

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, works_origin_id FROM works WHERE works_origin = 'CPDL'"
        )
        by_page = {str(r["works_origin_id"]): int(r["id"]) for r in await cur.fetchall()}

    inserts: list[tuple[int, int]] = []
    for pid, gids in page_genres.items():
        wid = by_page.get(str(pid))
        if wid is None:
            continue
        for gid in gids:
            inserts.append((wid, gid))

    unmatched = sorted(
        ((k, v) for k, v in distinct.items() if genre_of(k) is None and "=" not in k),
        key=lambda x: -x[1],
    )
    print({
        "paginas_con_genero": len(page_genres), "relaciones": len(inserts),
        "valores_distintos": len(distinct), "valores_ruido": skipped,
        "sin_mapear(no ruido)": len(unmatched),
    })
    print("  top sin mapear:", unmatched[:10])

    if dry_run:
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM work_genres WHERE works_id IN (SELECT id FROM works WHERE works_origin='CPDL')")
        for i in range(0, len(inserts), 2000):
            await cur.executemany(
                "INSERT IGNORE INTO work_genres (works_id, genres_id) VALUES (%s, %s)",
                inserts[i : i + 2000],
            )
        await cur.execute("DELETE FROM genre_mappings WHERE code LIKE 'cpdl:%'")
        rows = [(f"cpdl:{v}"[:60], g) for v, g in value_hits.items() if genre_of(v)]
        for i in range(0, len(rows), 2000):
            await cur.executemany(
                "INSERT IGNORE INTO genre_mappings (code, genre_id) VALUES (%s, %s)",
                rows[i : i + 2000],
            )
    await db.close()
    print(f"work_genres insertadas: {len(inserts)}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=r"G:\cpdl_chunks")
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    paths = sorted(Path(args.dir).glob("*.xml"))
    if not paths:
        raise SystemExit(f"no hay XML en {args.dir}")
    asyncio.run(run(paths, args.db, args.dry_run))


if __name__ == "__main__":
    main()
