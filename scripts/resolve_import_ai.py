"""Resuelve las filas pendientes de `works_person_import` con reglas + verificación en
Wikipedia/MusicBrainz (la "IA" disponible en el proyecto).

Qué hace, por fila pendiente:
1. **Anónimos**: `anonymous`, `trad`, `anon.`, `unknown`, `urheber unbekannt`… → se dan por
   asignadas (marca resuelta) sin crear persona: el dato vive en `works`.
2. **Extrae rol y nombre** del texto: `music by X`, `composed by X`, `lyrics by X`,
   `arr. by X`… Aunque la fila venga como `artist`, si el texto dice "composer" se trata
   como compositor. **Arreglistas y artistas NO se aceptan como compositores**: van a su
   rol (3 arreglista / 10 intérprete) y nunca pasan el control de "reconocido como
   compositor".
3. **Reconocimiento** (control de compositor): el nombre debe existir en `persons`/
   `persons_aliases`, en `persons_authority`, o **verificarse en Wikipedia/MusicBrainz
   como persona**. Si no pasa el control, no se crea nada (queda para revisión).
4. Crea/enlaza la persona con el rol correcto en `works_person_roles` y marca la fila como
   resuelta.

Uso:
    .venv\\Scripts\\python.exe scripts/resolve_import_ai.py --dry-run --limit 50
    .venv\\Scripts\\python.exe scripts/resolve_import_ai.py --limit 500 --roles composer
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import re
import sys
import unicodedata
import urllib.parse
import uuid
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.composer_names import normalize_composer_name  # noqa: E402
from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from link_works_person_import import clean_raw, compact  # noqa: E402

ROLE_COMPOSER = 1
ROLE_LYRICS = 2
ROLE_ARRANGER = 3

_UA = {
    "User-Agent": "OSAP-Storage/1.0 (https://openmusicrepository.com; admin@openmusicrepository.com)"
}
_WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
_WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary"
_MB_ARTIST = "https://musicbrainz.org/ws/2/artist"

_ANON = re.compile(
    r"^\s*(anonymous|anon\.?|trad\.?|traditional|unknown|desconocido|various|"
    r"urheber unbekannt.*|attrib\.?.*)\s*$",
    re.I,
)
_PREFIX = re.compile(
    r"^\s*(?:music|música|melody|tune|composer|composed|comp\.?)\s*[:\-]\s*", re.I
)
_BARE_ROLE = re.compile(
    r"^\s*(composer|composed|music|música|melody|tune|arranger|arr|lyrics?|words|text|"
    r"orchestrator|transcriber|editor|performer|singer)\s*$",
    re.I,
)
_MUSIC_BY = re.compile(
    r"^(?:music|música)\s+by\s+(.+?)(?:\s*(?:;|,)?\s*(?:lyrics?|words|text)\s+by\b|$)", re.I
)
_ARR = re.compile(
    r"^(?:arr(?:anged|angement)?\.?|arm\.?)\s*(?:by)?\s*[:.]?\s*(.+?)"
    r"(?:\s*(?:,|;)?\s*(?:composed|transcribed|orchestrated|edited)\b.*|$)", re.I
)
_COMPOSED_BY = re.compile(
    r"^(?:composed|comp\.)\s*(?:by)?\s*[:.]?\s*(.+?)"
    r"(?:\s*(?:,|;)?\s*(?:arr(?:anged|\.)?|transcribed|orchestrated|edited)\b.*|$)", re.I
)
_ARR_FROM = re.compile(
    r"^(?:arr(?:anged|angement)?|arm)\.?\s+from\s+(.+?)\s+by\s+(.+?)(?:\s+\d{4})?\s*$", re.I
)
_ARR_INLINE = re.compile(
    r"^(.*?)\s+arr(?:anged)?\.?\s*(?:by)?\s*[:.]?\s*(.+)$", re.I
)
_ARR_PAREN = re.compile(r"\(\s*arr(?:anged)?\.?\s*(?:by)?\s*[:.]?\s*([^)]+)\)", re.I)
_SPLIT_NAMES = re.compile(r"\s*(?:,|\band\b|&|\by\b|\bi\b|\be\b)\s*", re.I)
_LYRICS_BY = re.compile(r"(?:lyrics?|words|text)\s+by\s+(.+)$", re.I)
_ORCH = re.compile(r"^(?:orchestrated|orchestration)\s+by\s+(.+)$", re.I)
_TRANSCRIBED = re.compile(
    r"^(?:transcribed|transcription|transcr\.?)\s*(?:by)?\s*[:.]?\s*(.+)$", re.I
)
_EDITED = re.compile(r"^(?:edited|ed\.?)\s*(?:by)?\s*[:.]?\s*(.+)$", re.I)
_COMPOSER_TAG = re.compile(r"^(.+?)\s*[\(\[]\s*comp(?:oser|\.)?\s*[\)\]]$", re.I)
_BY = re.compile(r"^(?:by\s+)?(.+?)\s+by\s+(.+)$", re.I)
_TRAILING_ROLE = re.compile(
    r"[\s,;:.-]*(composer|compositor|lyricist|lyrics|arranger|orchestrator|transcriber|"
    r"editor|performer|singer|pianist)\s*$",
    re.I,
)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    t = t.lower().replace("_", " ")
    return re.sub(r"\s+", " ", t).strip()


def _clean_name(raw: str) -> str:
    name = (raw or "").strip(" ;,.-—–\t")
    name = _TRAILING_ROLE.sub("", name).strip(" ;,.-—–\t")
    name = re.sub(r"\s*\((?:arr|ed|comp)[^)]*\)\s*$", "", name, flags=re.I)
    # Restos pegados sin separador: "JoeArr." / "MatusArranged".
    name = re.split(r"(?<=[a-z])(?:Arr\.|Arranged|Transcribed|Orchestrated|Edited)", name,
                    flags=re.I)[0]
    # Años sueltos y tonalidades al final ("... 1848", "... C major", "... in D").
    name = re.sub(r"\s+\d{4}\s*$", "", name)
    name = re.sub(r"\s+(?:in\s+)?[A-G](?:\s*(?:major|minor|maj|min))?\s*$", "", name)
    name = re.sub(r"\s*\b(?:satb|ssatb|sattb|ttbb|ssaa|sab|unison)\b\s*$", "", name, flags=re.I)
    # Posesivo + título de obra: "Joe Buchanan's Scottish Tome" -> "Joe Buchanan".
    name = re.split(r"'s\s+", name, maxsplit=1)[0]
    name = re.sub(r"\s+", " ", name)
    return name.strip(" ;,.-—–\t")


def extract(text: str) -> tuple[list[tuple[int, str]], bool]:
    """Devuelve ([(role_id, nombre)], es_anonimo)."""
    raw = clean_raw(text)
    if _ANON.match(raw):
        return [], True
    # Separa palabras de rol pegadas ("ShaimanLyrics by ...").
    raw = re.sub(r"(?<=[a-z])(?=(?:Lyrics|Words|Text|Arr|Composed|Music)\b)", " ", raw)
    # Quita el prefijo de rol ("Composer:", "Music:") deja el nombre o la etiqueta.
    raw = _PREFIX.sub("", raw).strip()
    if _BARE_ROLE.match(raw):
        return [], False
    found: list[tuple[int, str]] = []
    # Arreglista entre paréntesis: "X (arr. Y)".
    paren = _ARR_PAREN.search(raw)
    if paren:
        for piece in _SPLIT_NAMES.split(paren.group(1)):
            if piece.strip():
                found.append((ROLE_ARRANGER, _clean_name(piece)))
        raw = _ARR_PAREN.sub("", raw).strip()
    # Arreglista inline sin "by": "Ludwig van Beethoven Arr. Donovan DiIorio".
    inline = _ARR_INLINE.match(raw) if raw else None
    if inline and not _ARR_FROM.match(raw):
        for piece in _SPLIT_NAMES.split(_clean_name(inline.group(1))):
            if piece.strip():
                found.append((ROLE_COMPOSER, _clean_name(piece)))
        for piece in _SPLIT_NAMES.split(inline.group(2)):
            if piece.strip():
                found.append((ROLE_ARRANGER, _clean_name(piece)))
        raw = ""
    # "Arr from <compositor> by <arreglista> [año]": dos roles distintos.
    arr_from = _ARR_FROM.search(raw) if raw else None
    if arr_from:
        found.append((ROLE_COMPOSER, _clean_name(arr_from.group(1))))
        found.append((ROLE_ARRANGER, _clean_name(arr_from.group(2))))
    composer = _MUSIC_BY.search(raw) if raw else None
    if composer:
        for piece in _SPLIT_NAMES.split(composer.group(1)):
            if piece.strip():
                found.append((ROLE_COMPOSER, _clean_name(piece)))
    lyrics = _LYRICS_BY.search(raw) if raw else None
    if lyrics:
        for piece in _SPLIT_NAMES.split(lyrics.group(1)):
            if piece.strip():
                found.append((ROLE_LYRICS, _clean_name(piece)))
    arr = None if (arr_from or not raw) else _ARR.search(raw)
    if arr:
        for piece in _SPLIT_NAMES.split(arr.group(1)):
            if piece.strip():
                found.append((ROLE_ARRANGER, _clean_name(piece)))
    orch = _ORCH.search(raw) if raw else None
    if orch:
        found.append((4, _clean_name(orch.group(1))))
    trans = _TRANSCRIBED.search(raw) if raw else None
    if trans:
        found.append((5, _clean_name(trans.group(1))))
    edited = _EDITED.search(raw) if raw else None
    if edited:
        found.append((6, _clean_name(edited.group(1))))
    composed = _COMPOSED_BY.search(raw) if raw else None
    if composed:
        for piece in _SPLIT_NAMES.split(composed.group(1)):
            if piece.strip():
                found.append((ROLE_COMPOSER, _clean_name(piece)))
    tagged = _COMPOSER_TAG.match(raw) if raw else None
    if tagged:
        found.append((ROLE_COMPOSER, _clean_name(tagged.group(1))))
    has_composer = any(role == ROLE_COMPOSER for role, _ in found)
    if not has_composer and raw and "'s " in raw:
        # "Joe Buchanan's Scottish Tome" → compositor "Joe Buchanan".
        found.append((ROLE_COMPOSER, _clean_name(raw.split("'s ", 1)[0])))
    if not has_composer and raw:
        by = _BY.match(raw)
        if by:
            found.append((ROLE_COMPOSER, _clean_name(by.group(2))))
    if not any(role == ROLE_COMPOSER for role, _ in found) and raw:
        # Sin compositor explícito: el texto puede ser una lista de nombres
        # ("Loïc Nottet i Beverly Jo Scott") o un nombre suelto tras "Composer:".
        # Se proponen como compositores y el llamante aplica el control de reconocido.
        for piece in _SPLIT_NAMES.split(_clean_name(raw)):
            if piece.strip():
                found.append((ROLE_COMPOSER, _clean_name(piece)))
    # Deduplica conservando orden y descartando nombres vacíos/cortos.
    out: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for role, name in found:
        name = name.strip()
        if len(name) < 3 or not normalize_composer_name(name):
            continue
        if _BARE_ROLE.match(name):
            continue
        key = (role, normalize_composer_name(name))
        if key not in seen:
            seen.add(key)
            out.append((role, name))
    return out, False


class Verifier:
    """Verifica si un nombre es una persona/compositor conocido (Wikipedia/MusicBrainz)."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._cache: dict[str, dict | None] = {}

    async def check(self, name: str) -> dict | None:
        key = _norm(name)
        if key in self._cache:
            return self._cache[key]
        result: dict | None = None
        try:
            resp = await self._client.get(
                _WIKI_SEARCH,
                params={"action": "query", "list": "search", "srsearch": name,
                        "format": "json", "srlimit": 1},
                headers=_UA,
            )
            hits = (resp.json().get("query") or {}).get("search") or []
            if hits:
                title = hits[0]["title"]
                k = _norm(title)
                looks_person = key.split()[-1] in k and len(key.split()) <= 5
                summary = await self._client.get(
                    f"{_WIKI_SUMMARY}/{urllib.parse.quote(title.replace(' ', '_'))}",
                    headers=_UA,
                )
                if summary.status_code == 200:
                    data = summary.json()
                    desc = (data.get("description") or "").lower()
                    is_person = any(
                        w in desc
                        for w in ("composer", "musician", "songwriter", "lyricist",
                                  "conductor", "pianist", "organist", "singer")
                    )
                    if is_person and looks_person:
                        result = {"source": "wikipedia", "title": title,
                                  "url": data.get("content_urls", {})
                                  .get("desktop", {}).get("page")}
        except (httpx.HTTPError, ValueError):
            result = None
        self._cache[key] = result
        return result

    async def musicbrainz(self, name: str) -> dict | None:
        key = "mb:" + _norm(name)
        if key in self._cache:
            return self._cache[key]
        result: dict | None = None
        try:
            resp = await self._client.get(
                _MB_ARTIST,
                params={"query": f'artist:"{name}"', "fmt": "json", "limit": 3},
                headers=_UA,
            )
            for artist in (resp.json().get("artists") or []):
                if (artist.get("type") or "") == "Person" and float(artist.get("score") or 0) >= 90:
                    result = {"source": "musicbrainz", "id": artist.get("id"),
                              "title": artist.get("name")}
                    break
        except (httpx.HTTPError, ValueError):
            result = None
        self._cache[key] = result
        await asyncio.sleep(1.1)  # cortesía con MusicBrainz
        return result


async def run(db_name: str, roles: list[str], limit: int | None, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    by_norm: dict[str, set[str]] = defaultdict(set)
    by_compact: dict[str, set[str]] = defaultdict(set)
    authority: dict[str, dict] = {}

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT persons_id, persons_name FROM persons")
        for r in await cur.fetchall():
            by_norm[normalize_composer_name(r["persons_name"])].add(r["persons_id"])
            by_compact[compact(r["persons_name"])].add(r["persons_id"])
        await cur.execute(
            "SELECT person_id, person_aliases_normalized_alias, person_aliases_alias "
            "FROM persons_aliases"
        )
        for r in await cur.fetchall():
            by_norm[str(r["person_aliases_normalized_alias"])].add(r["person_id"])
            by_compact[compact(r["person_aliases_alias"])].add(r["person_id"])
        # Autoridad por nombre completo normalizado y por clave canónica.
        await cur.execute(
            "SELECT authority_id, persons_authority_canonical_name AS name, "
            "persons_authority_wikidata_id AS wid, persons_authority_viaf_id AS viaf, "
            "persons_authority_imslp_id AS imslp FROM persons_authority"
        )
        for r in await cur.fetchall():
            key = normalize_composer_name(r["name"])
            if key:
                authority.setdefault(key, dict(r))

        roles_ph = ", ".join(["%s"] * len(roles))
        sql = (
            f"SELECT id, works_id, works_person_import_name AS name, "
            f"works_person_import_role AS role FROM works_person_import "
            f"WHERE works_person_import_resolved = 0 AND works_person_import_role IN ({roles_ph}) "
            f"ORDER BY id"
        )
        params: list = list(roles)
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    links: list[tuple[int, str, int]] = []
    resolved_ids: list[int] = []
    new_persons: list[tuple[str, str, dict | None]] = []
    review: list[dict] = []
    stats = {"filas": len(rows), "anonimos": 0, "enlazadas": 0, "creadas": 0,
             "verificadas": 0, "del_origen": 0, "creadas_rol": 0, "sin_reconocer": 0, "sin_patron": 0}

    async with httpx.AsyncClient(timeout=12) as client:
        verifier = Verifier(client)
        for r in rows:
            text = str(r["name"])
            found, is_anon = extract(text)
            if is_anon:
                resolved_ids.append(int(r["id"]))
                stats["anonimos"] += 1
                continue
            if not found:
                stats["sin_patron"] += 1
                continue
            for role_id, name in found:
                key = normalize_composer_name(name)
                pids = by_norm.get(key) or by_compact.get(compact(name))
                pid: str | None = next(iter(pids)) if pids and len(pids) == 1 else None
                if not pid and len(pids or ()) > 1:
                    pid = sorted(pids)[0]
                if not pid and key in authority:
                    auth = authority[key]
                    pid = str(uuid.uuid4())
                    new_persons.append((pid, str(auth["name"]), auth))
                    by_norm.setdefault(key, set()).add(pid)
                    stats["creadas"] += 1
                if not pid and role_id != ROLE_COMPOSER:
                    # Arreglistas/letristas/transcriptores NO pasan el control de
                    # "reconocido como compositor": el propio texto declara su rol.
                    pid = str(uuid.uuid4())
                    new_persons.append((pid, name, None))
                    by_norm.setdefault(key, set()).add(pid)
                    stats["creadas_rol"] += 1
                if not pid and role_id == ROLE_COMPOSER:
                    # Si el origen ya decía "composer", el nombre extraído vale; si venía
                    # como "artist", exigimos verificación (control de reconocido).
                    if str(r["role"]) == "composer":
                        pid = str(uuid.uuid4())
                        new_persons.append((pid, name, None))
                        by_norm.setdefault(key, set()).add(pid)
                        stats["del_origen"] += 1
                    else:
                        hit = await verifier.check(name) or await verifier.musicbrainz(name)
                        if hit:
                            pid = str(uuid.uuid4())
                            new_persons.append((pid, name, None))
                            by_norm.setdefault(key, set()).add(pid)
                            stats["verificadas"] += 1
                if pid:
                    links.append((int(r["works_id"]), pid, role_id))
                    resolved_ids.append(int(r["id"]))
                    stats["enlazadas"] += 1
                else:
                    stats["sin_reconocer"] += 1
                    if role_id == ROLE_COMPOSER:
                        review.append({"import_id": r["id"], "works_id": r["works_id"],
                                       "texto": text, "candidato": name})

    print(json.dumps(stats, ensure_ascii=False))
    print(f"personas nuevas: {len(new_persons)} | filas para revisión: {len(review)}")

    if dry_run:
        for item in review[:15]:
            print("  REV:", item["candidato"], "|", item["texto"][:70])
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for pid, name, auth in new_persons:
            await cur.execute(
                "INSERT IGNORE INTO persons (persons_id, persons_name, persons_visible, "
                "persons_status, persons_source_system) VALUES (%s, %s, 1, 'active', 'web')",
                (pid, name[:255]),
            )
            if auth:
                for id_type, value in (("wikidata_qid", auth.get("wid")),
                                       ("viaf", auth.get("viaf")),
                                       ("imslp", auth.get("imslp"))):
                    if value:
                        await cur.execute(
                            "INSERT INTO persons_identifiers (persons_id, "
                            "persons_identifiers_type, persons_identifiers_value, "
                            "persons_identifiers_source) VALUES (%s, %s, %s, 'wikidata')",
                            (pid, id_type, str(value)),
                        )
        if links:
            await cur.executemany(
                "INSERT IGNORE INTO works_person_roles (works_person_roles_work_id, "
                "works_person_roles_person_id, works_person_roles_role_id) VALUES (%s,%s,%s)",
                links,
            )
        for i in range(0, len(resolved_ids), 1000):
            chunk = resolved_ids[i : i + 1000]
            ph = ", ".join(["%s"] * len(chunk))
            await cur.execute(
                f"UPDATE works_person_import SET works_person_import_resolved = 1 "
                f"WHERE id IN ({ph})",
                chunk,
            )
    await db.close()
    print(f"personas: {len(new_persons)} | relaciones: {len(links)} | marcadas: {len(resolved_ids)}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--roles", default="composer,artist")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.db, [r.strip() for r in args.roles.split(",") if r.strip()],
                    args.limit, args.dry_run))


if __name__ == "__main__":
    main()