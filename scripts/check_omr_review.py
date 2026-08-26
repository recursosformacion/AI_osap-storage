#!/usr/bin/env python
"""Revisión de OMR: duplicados y diferencias entre ficheros MusicXML/PDF.

Prepara una muestra de la revisión del corpus OMR:

1. Duplicados binarios: busca ficheros con el mismo SHA-256 (idénticos byte a byte).
   Como el corpus aún no tiene `sha256` en `files`, compara por hash del contenido
   de los ficheros físicos (los que existan en el árbol local).

2. Diferencias entre variantes de la misma obra (mismo título+compositor, ficheros
   distintos): extrae los MusicXML de dos `.mxl` (zip con `score.xml`) y muestra las
   primeras diferencias estructurales (título, compás, notas) y un resumen.

Uso (en osap-storage, con PYTHONPATH=osap-storage):
    python scripts/check_omr_review.py [--mxl-root devdata/mxl] [--limit 4]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import pymysql


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _mxl_xml(path: Path) -> str:
    """Extrae el score.xml de un .mxl (MusicXML comprimido)."""
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith(".xml") or name.endswith("score.mxl") or "score" in name:
                return zf.read(name).decode("utf-8", "replace")
        # Sin XML dentro: devuelve el contenido tal cual (a veces es XML plano).
        return path.read_text(encoding="utf-8", errors="replace")


def _summary_diff(xml_a: str, xml_b: str) -> dict[str, object]:
    """Primeras diferencias entre dos MusicXML (por líneas no vacías)."""
    a_lines = [line.strip() for line in xml_a.splitlines() if line.strip()]
    b_lines = [line.strip() for line in xml_b.splitlines() if line.strip()]
    n = min(len(a_lines), len(b_lines))
    diffs: list[tuple[int, str, str]] = []
    for i in range(n):
        if a_lines[i] != b_lines[i]:
            diffs.append((i + 1, a_lines[i][:90], b_lines[i][:90]))
            if len(diffs) >= 5:
                break
    if not diffs and len(a_lines) != len(b_lines):
        diffs.append((n + 1, f"[{len(a_lines)} líneas]", f"[{len(b_lines)} líneas]"))
    return {
        "len_a": len(a_lines),
        "len_b": len(b_lines),
        "diffs": diffs,
        "identical_lines": not diffs,
    }


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mxl-root", default="devdata/mxl")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--db-host", default="127.0.0.1")
    parser.add_argument("--db-user", default="osap2027")
    parser.add_argument("--db-password", default="2027osapdb")
    parser.add_argument("--db-name", default="osap-storage")
    args = parser.parse_args()

    root = Path(args.mxl_root)
    if not root.is_dir():
        print(f"no existe {root} (los ficheros OMR están en el bucket/R2 en prod)")
        return 0

    print(f"== 1) Duplicados por SHA-256 en {root} ==")
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for p in root.rglob("*.mxl"):
        by_hash[_hash_file(p)].append(p)
    dup_groups = {h: paths for h, paths in by_hash.items() if len(paths) > 1}
    if dup_groups:
        for h, paths in list(dup_groups.items())[:args.limit]:
            print(f"  sha256={h[:16]}... n={len(paths)}")
            for p in paths[:3]:
                print(f"    {p} {p.stat().st_size} bytes")
    else:
        print("  sin duplicados binarios en la muestra local")

    print("\n== 2) Variantes de la misma obra (título+compositor repetidos) ==")
    conn = pymysql.connect(
        host=args.db_host, user=args.db_user, password=args.db_password,
        database=args.db_name, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        # mapear los CIDs físicos locales a su obra en la BD
        local_cids = [p.name for p in root.rglob("*.mxl")]
        placeholders = ",".join(["%s"] * len(local_cids)) if local_cids else "NULL"
        cur.execute(
            f"SELECT f.name AS fname, w.id AS work_id, w.title, w.composer "
            f"FROM files f JOIN archive_entries ae ON ae.file_id=f.id "
            f"JOIN works w ON w.id=ae.work_id "
            f"WHERE f.name IN ({placeholders})",
            local_cids,
        )
        rows = cur.fetchall()
        by_work: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in rows:
            by_work[(str(r["title"]), str(r["composer"] or ""))].append(r)

        cur.execute(
            "SELECT w.title, w.composer, COUNT(*) AS n FROM works w "
            "WHERE w.title IS NOT NULL GROUP BY w.title, w.composer HAVING n > 1 "
            "ORDER BY n DESC LIMIT %s",
            (args.limit,),
        )
        groups = cur.fetchall()
    conn.close()

    print(f"  ({len(local_cids)} ficheros físicos en {root}; "
          f"{sum(len(v) for v in by_work.values())} mapeados a obras)")
    for g in groups:
        title = str(g["title"])
        composer = str(g["composer"] or "")
        key = (title, composer)
        local = by_work.get(key, [])
        if len(local) < 2:
            continue
        print(f"\n  Obra: {title} | {composer} ({g['n']} variantes; "
              f"{len(local)} en local)")
        paths = []
        for r in local[:2]:
            p = next((x for x in root.rglob(r["fname"])), None)
            if p:
                paths.append(p)
        if len(paths) < 2:
            continue
        print(f"    a) {paths[0].name} ({paths[0].stat().st_size} B)")
        print(f"    b) {paths[1].name} ({paths[1].stat().st_size} B)")
        xml_a = _mxl_xml(paths[0])
        xml_b = _mxl_xml(paths[1])
        sd = _summary_diff(xml_a, xml_b)
        if sd["identical_lines"]:
            print("    -> contenido MusicXML IDÉNTICO (mismo score.xml)")
        else:
            print(f"    -> diferencias: líneas a={sd['len_a']} b={sd['len_b']}")
            for lineno, la, lb in sd["diffs"]:  # type: ignore[assignment]
                print(f"       L{lineno}\n         A: {la}\n         B: {lb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
