"""Puebla `cpdl_editions` + `cpdl_edition_files` + `cpdl_edition_persons` desde los XML CPDL.

Modela el `payload_json` de cada página CPDL: la obra (`works`, ya importada) tiene N
ediciones (cada una con su `cpdlno` y licencia), cada edición tiene N ficheros (nombre+tipo)
y un editor, que se modela como **persona** con rol 6 (Editor/a Musical) sobre la edición.

Uso:
    .venv\\Scripts\\python.exe scripts/import_cpdl_editions.py --dry-run
    .venv\\Scripts\\python.exe scripts/import_cpdl_editions.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.composer_names import normalize_composer_name  # noqa: E402
from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

_spec = importlib.util.spec_from_file_location("icw", ROOT / "scripts" / "import_cpdl_works.py")
_icw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_icw)

ROLE_EDITOR = 6
SOURCE = "cpdl"
_TYPES = {
    ".pdf": "PDF", ".mxl": "MXL", ".xml": "MusicXML", ".mid": "MIDI", ".midi": "MIDI",
    ".mp3": "MP3", ".capx": "CAPX", ".mus": "MUS", ".sib": "SIB", ".mscz": "MSCZ",
}


def file_type(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return _TYPES.get(suffix, suffix.lstrip(".").upper()[:16] or "OTHER")


def compact(value: str) -> str:
    return normalize_composer_name(value).replace(" ", "")


async def run(paths: list[Path], db_name: str, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    by_norm: dict[str, set[str]] = defaultdict(set)
    by_compact: dict[str, set[str]] = defaultdict(set)
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
        await cur.execute("SELECT id, works_origin_id FROM works WHERE works_origin = 'CPDL'")
        work_by_page = {str(r["works_origin_id"]): int(r["id"]) for r in await cur.fetchall()}

    # 1) Parseo de ediciones (cpdlno, licencia, editor, ficheros).
    parsed: list[tuple[int, int, str, str, list[str]]] = []
    for path in paths:
        for page_id, title, text in _element_pages(path):
            rec = _icw._parse_page(page_id, title, text)
            parsed.extend(_editions(rec))

    # 2) Resolución de editores.
    editors = {ed[3] for ed in parsed if ed[3]}
    new_persons: list[tuple[str, str]] = []
    editor_pid: dict[str, str] = {}
    for name in sorted(editors):
        key = normalize_composer_name(name)
        pids = by_norm.get(key) or by_compact.get(compact(name))
        if pids:
            editor_pid[name] = sorted(pids)[0]
            continue
        pid = str(uuid.uuid4())
        new_persons.append((pid, name[:255]))
        by_norm.setdefault(key, set()).add(pid)
        editor_pid[name] = pid

    mapped = sum(1 for ed in parsed if str(ed[0]) in work_by_page)
    print({
        "ediciones": len(parsed), "con_obra": mapped,
        "editores_distintos": len(editors), "personas_nuevas": len(new_persons),
        "ficheros": sum(len(ed[4]) for ed in parsed),
    })

    if dry_run:
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM cpdl_editions")  # cascada: ficheros + editores
        for pid, name in new_persons:
            await cur.execute(
                "INSERT IGNORE INTO persons (persons_id, persons_name, persons_visible, "
                "persons_status, persons_source_system) VALUES (%s, %s, 1, 'active', %s)",
                (pid, name, SOURCE),
            )
            await cur.execute(
                "INSERT IGNORE INTO persons_aliases (person_id, person_aliases_alias, "
                "person_aliases_normalized_alias) VALUES (%s, %s, %s)",
                (pid, name, normalize_composer_name(name)[:255]),
            )
        for page_id, cpdlno, license_, editor, files in parsed:
            wid = work_by_page.get(str(page_id))
            if wid is None:
                continue
            await cur.execute(
                "INSERT INTO cpdl_editions (works_id, cpdl_editions_cpdlno, "
                "cpdl_editions_license) VALUES (%s, %s, %s)",
                (wid, cpdlno, license_[:120]),
            )
            eid = cur.lastrowid
            if files:
                await cur.executemany(
                    "INSERT INTO cpdl_edition_files (cpdl_editions_id, cpdl_edition_files_name, "
                    "cpdl_edition_files_type) VALUES (%s, %s, %s)",
                    [(eid, f[:512], file_type(f)) for f in files],
                )
            if editor:
                await cur.execute(
                    "INSERT INTO cpdl_edition_persons (cpdl_editions_id, persons_id, roles_id, "
                    "cpdl_edition_persons_name) VALUES (%s, %s, %s, %s)",
                    (eid, editor_pid.get(editor), ROLE_EDITOR, editor[:255]),
                )
    await db.close()
    print(f"ediciones insertadas: {len(parsed)}")


def _element_pages(path: Path):
    from xml.etree import ElementTree

    for _event, elem in ElementTree.iterparse(path, events=("end",)):
        if elem.tag != _icw.NS + "page":
            continue
        title = (elem.findtext(_icw.NS + "title") or "").strip()
        pid = elem.findtext(_icw.NS + "id") or ""
        text = elem.findtext(".//" + _icw.NS + "text") or ""
        elem.clear()
        if pid.isdigit() and _icw._looks_like_work(text):
            yield int(pid), title, text


def _editions(rec: dict) -> list[tuple[int, int, str, str, list[str]]]:
    out = []
    seen: set[int] = set()
    for ed in json.loads(rec["payload_json"])["editions"]:
        cpdlno = str(ed.get("cpdlno") or "")
        if not cpdlno.isdigit() or int(cpdlno) == 0 or int(cpdlno) in seen:
            continue
        seen.add(int(cpdlno))
        out.append(
            (rec["page_id"], int(cpdlno), str(ed.get("license") or ""),
             str(ed.get("editor") or "").strip(), list(ed.get("files") or []))
        )
    return out


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
