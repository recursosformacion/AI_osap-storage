"""Importador de páginas CPDL (exports MediaWiki de ChoralWiki) a `works`.

Sustituye al antiguo `import_cpdl_pages.py` (que escribía en `cpdl_pages`): el
corpus CPDL pasa a ser filas de `works` con `works_origin='CPDL'` y
`works_origin_id` = id de página MediaWiki (numérico, único y estable).

Extrae de cada página:
- `title`, `composer`, `catalogue_hint`, `arrangement_hint`
- `voicing`, `instrumentation`, `genre`, `language` (arrays)
- `license`, `n_editions`, `payload_json` (ediciones)

Escribe:
- `works` (origin/origin_id/title/catalogue/license/voicing)
- `works_person_import` (composer, sin resolver)
- `languages` + `work_language` (idiomas)

Solo importa páginas que parezcan obras (tienen `{{CPDLno|...}}` o `{{Voicing|...}}`).

Uso:
    .venv\\Scripts\\python.exe scripts/import_cpdl_works.py --dir G:\\cpdl_chunks
    .venv\\Scripts\\python.exe scripts/import_cpdl_works.py --files G:\\x.xml --db osap-storage_new --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

NS = "{http://www.mediawiki.org/xml/export-0.11/}"

# Idioma CPDL (nombre) -> (código ISO 639-1, nombre normalizado)
LANGUAGES: dict[str, tuple[str, str]] = {
    "latin": ("la", "Latin"),
    "english": ("en", "English"),
    "italian": ("it", "Italian"),
    "german": ("de", "German"),
    "french": ("fr", "French"),
    "czech": ("cs", "Czech"),
    "spanish": ("es", "Spanish"),
    "portuguese": ("pt", "Portuguese"),
    "dutch": ("nl", "Dutch"),
    "church slavonic": ("cu", "Church Slavonic"),
    "latvian": ("lv", "Latvian"),
    "hebrew": ("he", "Hebrew"),
    "swedish": ("sv", "Swedish"),
    "galician": ("gl", "Galician"),
    "ukrainian": ("uk", "Ukrainian"),
    "danish": ("da", "Danish"),
    "norwegian": ("no", "Norwegian"),
    "russian": ("ru", "Russian"),
    "lombard": ("lmo", "Lombard"),
    "basque": ("eu", "Basque"),
    "catalan": ("ca", "Catalan"),
    "polish": ("pl", "Polish"),
    "greek": ("el", "Greek"),
    "hungarian": ("hu", "Hungarian"),
    "finnish": ("fi", "Finnish"),
    "estonian": ("et", "Estonian"),
    "romanian": ("ro", "Romanian"),
    "croatian": ("hr", "Croatian"),
    "slovenian": ("sl", "Slovenian"),
    "slovak": ("sk", "Slovak"),
    "turkish": ("tr", "Turkish"),
    "arabic": ("ar", "Arabic"),
    "japanese": ("ja", "Japanese"),
    "chinese": ("zh", "Chinese"),
    "korean": ("ko", "Korean"),
    "welsh": ("cy", "Welsh"),
    "irish": ("ga", "Irish"),
    "german (austrian)": ("de", "German"),
}
_SKIP_LANG = {"", "unknown", "unspecified", "-"}

_CPDLNO = re.compile(r"\{\{\s*CPDLno\s*\|\s*\d+", re.I)
_HAS_VOICING = re.compile(r"\{\{\s*Voicing\s*\|", re.I)


def _clean(s: str) -> str:
    s = re.sub(r"\[\[Media:[^|\]]*\|[^]]*\]\]", "", s)
    s = re.sub(r"\[\[[^|\]]*\|([^]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^]]*)\]\]", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"''+", "", s)
    s = re.sub(r"\{\{#?\w+:?[^}]*\}\}", "", s)
    return s.replace("&nbsp;", " ").strip()


def _tmpl(text: str, name: str) -> str:
    m = re.search(r"\{\{\s*" + re.escape(name) + r"\|([^}]*)\}\}", text)
    return _clean(m.group(1).split("|")[0]) if m else ""


def _tmpl_multi(text: str, name: str) -> list[str]:
    m = re.search(r"\{\{\s*" + re.escape(name) + r"\|([^}]*)\}\}", text)
    return [_clean(p) for p in m.group(1).split("|") if _clean(p)] if m else []


def _parse_page(page_id: int, title: str, text: str) -> dict:
    composer = _clean(title.rsplit("(", 1)[-1].rstrip(")")) if title.endswith(")") else ""
    cm = re.search(r"\{\{\s*Composer\|([^}|]*)", text)
    if cm:
        composer = _clean(cm.group(1))
    catalogue = ""
    for pat in (r"KV\s*\d+", r"K\.\s*\d+", r"CG\s*\d+", r"Op\.\s*[\dNo. ,]+", r"D\.\s*\d+", r"BWV\s*\d+"):
        c = re.search(pat, title)
        if c:
            catalogue = c.group(0)
            break
    editions = []
    for chunk in re.split(r"\n\s*\*\s*", text)[1:]:
        m = re.search(r"\{\{\s*CPDLno\|(\d+)\}\}", chunk)
        if not m:
            continue
        files = re.findall(
            r"\[\[Media:([^\]|]+\.(?:pdf|mxl|mid|xml|mp3|mscz|capx|sib|mus))", chunk, re.I
        )
        ed = re.search(r"\{\{\s*Editor\|([^}|]+)", chunk)
        copy = re.search(r"\{\{\s*Copy(?:CC)?\|([^}|]+)", chunk)
        editions.append(
            {
                "cpdlno": m.group(1),
                "files": sorted({f.lower() for f in files}),
                "editor": _clean(ed.group(1)) if ed else "",
                "license": _clean(copy.group(1)) if copy else "",
            }
        )
    low = (text + title).lower()
    return {
        "page_id": page_id,
        "page_title": title,
        "title": _tmpl(text, "Title") or _clean(title),
        "composer": composer,
        "catalogue_hint": catalogue or None,
        "arrangement_hint": bool(
            re.search(r"arr(?:anged)? by|reformat|reduction|transcr(?:iption)?|piano acc", low)
        ),
        "voicing": _tmpl_multi(text, "Voicing"),
        "instrumentation": _tmpl_multi(text, "Instruments"),
        "genre": _tmpl_multi(text, "Genre"),
        "language": _tmpl_multi(text, "Language"),
        "license": editions[0]["license"] if editions else None,
        "n_editions": len(editions),
        "payload_json": json.dumps({"editions": editions[:50]}, ensure_ascii=False),
    }


def _looks_like_work(text: str) -> bool:
    return bool(_CPDLNO.search(text) or _HAS_VOICING.search(text))


def _lang(settings_lang: str) -> tuple[str, str] | None:
    key = settings_lang.strip().lower()
    if key in _SKIP_LANG:
        return None
    if key in LANGUAGES:
        return LANGUAGES[key]
    if re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{1,60}", settings_lang.strip()):
        return (settings_lang.strip()[:16], settings_lang.strip())
    return None


async def _ingest(paths: list[Path], db_name: str, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    settings = base.model_copy(update={"db_name": db_name})
    db = Database(settings)
    await db.connect()

    seen: set[int] = set()
    lang_ids: dict[str, int] = {}
    works = 0
    skipped = 0

    if not dry_run:
        async with db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM works WHERE works_origin = 'CPDL'")

    async with db.connection() as conn, conn.cursor() as cur:
        for path in paths:
            for _event, elem in ElementTree.iterparse(path, events=("end",)):
                if elem.tag != NS + "page":
                    continue
                title = (elem.findtext(NS + "title") or "").strip()
                page_id_txt = elem.findtext(NS + "id") or ""
                text = elem.findtext(".//" + NS + "text") or ""
                elem.clear()
                if not page_id_txt.isdigit():
                    continue
                page_id = int(page_id_txt)
                if page_id in seen:
                    continue
                seen.add(page_id)
                if not _looks_like_work(text):
                    skipped += 1
                    continue
                rec = _parse_page(page_id, title, text)
                if dry_run:
                    works += 1
                    continue

                await cur.execute(
                    """
                    INSERT INTO works
                        (works_origin, works_origin_id, works_title, works_catalogue,
                         works_license, works_voicing, works_instrumentation)
                    VALUES ('CPDL', %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(page_id),
                        rec["title"],
                        rec["catalogue_hint"],
                        rec["license"],
                        json.dumps(rec["voicing"], ensure_ascii=False),
                        json.dumps(rec["instrumentation"], ensure_ascii=False),
                    ),
                )
                work_id = cur.lastrowid
                works += 1

                if rec["composer"]:
                    await cur.execute(
                        "INSERT INTO works_person_import "
                        "(works_id, works_person_import_name, works_person_import_role, "
                        " works_person_import_source) VALUES (%s, %s, 'composer', 'cpdl')",
                        (work_id, rec["composer"]),
                    )

                for raw_lang in rec["language"]:
                    mapped = _lang(raw_lang)
                    if mapped is None:
                        continue
                    code, name = mapped
                    if code not in lang_ids:
                        await cur.execute(
                            "INSERT IGNORE INTO languages (languages_code, languages_name) "
                            "VALUES (%s, %s)",
                            (code, name),
                        )
                        await cur.execute(
                            "SELECT id FROM languages WHERE languages_code = %s", (code,)
                        )
                        row = await cur.fetchone()
                        lang_ids[code] = int(row["id"])
                    await cur.execute(
                        "INSERT IGNORE INTO work_language (works_id, languages_id) VALUES (%s, %s)",
                        (work_id, lang_ids[code]),
                    )

                if works % 2000 == 0:
                    await conn.commit()
                    print(f"  ... {works} works", flush=True)

        if not dry_run:
            await conn.commit()
    await db.close()
    print(f"works CPDL: {works} | páginas descartadas (no parecen obra): {skipped}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--files", nargs="*", type=Path, default=[])
    ap.add_argument("--dir", type=Path, default=None)
    ap.add_argument("--db", default="osap-storage_new")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    paths = list(args.files)
    if args.dir is not None:
        paths += sorted(args.dir.glob("*.xml"))
    if not paths:
        raise SystemExit("indica --files o --dir")
    asyncio.run(_ingest(paths, args.db, args.dry_run))


if __name__ == "__main__":
    main()
