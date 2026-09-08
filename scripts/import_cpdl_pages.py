"""Importador de páginas CPDL (exports MediaWiki de ChoralWiki) a `cpdl_pages`.

Lee uno o varios ficheros export XML (Special:Export de CPDL, p. ej.
G:\\ChoralWiki-20260903154414.xml), normaliza cada página (plantillas wiki) y hace
upsert por `page_title`. NO toca `works`: esta tabla es corpus de referencia para
identidad/fusión.

Uso:
    .venv\\Scripts\\python.exe scripts/import_cpdl_pages.py --files G:\\chunk1.xml G:\\chunk2.xml
    # o todo un directorio:
    .venv\\Scripts\\python.exe scripts/import_cpdl_pages.py --dir G:\\cpdl_chunks

Requiere las migraciones 035_cpdl_pages (tabla) y 036_cpdl_voicings (términos de
búsqueda por voicing). Idempotente: re-ejecutar reescribe la página y SUS términos.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from xml.etree import ElementTree

from application.services.cpdl_voicing import voicing_terms
from infrastructure.config import Settings
from infrastructure.db.connection import Database

NS = "{http://www.mediawiki.org/xml/export-0.11/}"


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


def _parse_page(title: str, text: str) -> dict:
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
        files = re.findall(r"\[\[Media:([^\]|]+\.(?:pdf|mxl|mid|xml|mp3|mscz|capx|sib|mus))", chunk, re.I)
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


async def _ingest_files(paths: list[Path]) -> None:
    db = Database(Settings())
    total = 0
    pages_seen = set()
    async with db.connection() as conn, conn.cursor() as cur:
        for path in paths:
            for _event, elem in ElementTree.iterparse(path, events=("end",)):
                if elem.tag != NS + "page":
                    continue
                title = (elem.findtext(NS + "title") or "").strip()
                if title in pages_seen:
                    elem.clear()
                    continue
                pages_seen.add(title)
                text = elem.findtext(".//" + NS + "text") or ""
                rec = _parse_page(title, text)
                voicing_json = json.dumps(rec["voicing"], ensure_ascii=False)
                await cur.execute(
                    """
                    INSERT INTO cpdl_pages
                        (page_title, title, composer, catalogue_hint, arrangement_hint,
                         voicing, instrumentation, genre, language, license, n_editions, payload_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        title = VALUES(title), composer = VALUES(composer),
                        catalogue_hint = VALUES(catalogue_hint), arrangement_hint = VALUES(arrangement_hint),
                        voicing = VALUES(voicing), instrumentation = VALUES(instrumentation),
                        genre = VALUES(genre), language = VALUES(language), license = VALUES(license),
                        n_editions = VALUES(n_editions), payload_json = VALUES(payload_json)
                    """,
                    (
                        rec["page_title"],
                        rec["title"],
                        rec["composer"],
                        rec["catalogue_hint"],
                        int(rec["arrangement_hint"]),
                        voicing_json,
                        json.dumps(rec["instrumentation"], ensure_ascii=False),
                        json.dumps(rec["genre"], ensure_ascii=False),
                        json.dumps(rec["language"], ensure_ascii=False),
                        rec["license"],
                        rec["n_editions"],
                        rec["payload_json"],
                    ),
                )
                # Términos de voicing derivados: la página sigue siendo ÚNICA; cada fila
                # relaciona la misma página con un término buscable. Se reescribe siempre
                # (idempotente) para reflejar el voicing más reciente del dump.
                await cur.execute("SELECT id FROM cpdl_pages WHERE page_title = %s", (rec["page_title"],))
                page_row = await cur.fetchone()
                if page_row is not None:
                    page_id = int(page_row["id"])
                    await cur.execute("DELETE FROM cpdl_voicings WHERE cpdl_page_id = %s", (page_id,))
                    terms = voicing_terms(voicing_json)
                    for term in terms:
                        await cur.execute(
                            "INSERT INTO cpdl_voicings (cpdl_page_id, term) VALUES (%s, %s)",
                            (page_id, term),
                        )
                total += 1
                if total % 2000 == 0:
                    await conn.commit()
                    print(f"  ... {total} páginas ({path.name})", flush=True)
                elem.clear()
        await conn.commit()
    print(f"total páginas ingeridas/actualizadas: {total}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--files", nargs="*", type=Path, default=[])
    ap.add_argument("--dir", type=Path, default=None)
    args = ap.parse_args()
    paths = list(args.files)
    if args.dir is not None:
        paths += sorted(args.dir.glob("*.xml"))
    if not paths:
        raise SystemExit("indica --files o --dir")
    asyncio.run(_ingest_files(paths))


if __name__ == "__main__":
    main()
