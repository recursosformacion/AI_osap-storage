"""Verificación de representaciones OMR (`index_representations`, osap-api).

Para cada rep `provider='omr' AND format='musicxml' AND available=1`:
  - extrae el `file_id` de la URL (…/api/download/{file_id});
  - localiza su `object_key` en osap-storage;
  - lee el fichero del espejo local G:\\osap-storage (idéntico a R2; fallback a R2 no
    incluido en esta pasada);
  - comprueba bytes>0 y que sea MusicXML válido (raíz score + ≥1 nota).

Solo LECTURA. Reanudable no aplica (informe agregado).

Uso:
    .venv\\Scripts\\python.exe scripts/verify_omr_representations.py --limit 5000 --workers 8
"""

from __future__ import annotations

import argparse
import concurrent.futures
import io
import os
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pymysql
from pymysql.cursors import DictCursor

G_ROOT = Path("G:/osap-storage")


def _validate_bytes(raw: bytes) -> tuple[bool, str | None]:
    xml = raw
    if raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith((".xml", ".musicxml")) and "meta-inf" not in name.lower():
                        xml = zf.read(name)
                        break
        except zipfile.BadZipFile:
            return False, "zip roto"
    if not xml:
        return False, "0 bytes"
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        return False, f"XML malformado: {exc}"
    tag = (root.tag or "").rsplit("}", 1)[-1]
    if tag not in ("score-partwise", "score-timewise"):
        return False, f"raíz no partiture: {tag}"
    notes = sum(1 for el in root.iter() if (el.tag or "").endswith("note"))
    if notes == 0:
        return False, "0 notas"
    return True, None


def _process_files(items: list[tuple[int, str]]) -> list[dict]:
    out: list[dict] = []
    for file_id, object_key in items:
        path = G_ROOT / object_key.lstrip("./")
        if not path.is_file():
            out.append({"file_id": file_id, "ok": False, "reason": "sin fichero local"})
            continue
        raw = path.read_bytes()
        ok, reason = _validate_bytes(raw)
        out.append(
            {
                "file_id": file_id,
                "ok": ok,
                "reason": reason or "ok",
                "size": len(raw),
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=max(4, os.cpu_count() or 4))
    ap.add_argument("--checkpoint", type=Path, default=Path(r"D:\Proyectos\AI_OSAP\_pruebas\omr_verify_checkpoint.txt"))
    args = ap.parse_args()

    api = pymysql.connect(
        host="127.0.0.1", user="osap2027", password="2027osapdb",
        database="osap-api", cursorclass=DictCursor,
    )
    st = pymysql.connect(
        host="127.0.0.1", user="osap2027", password="2027osapdb",
        database="osap-storage", cursorclass=DictCursor,
    )
    cur = api.cursor()
    query = (
        "SELECT id, work_id, download_url FROM index_representations "
        "WHERE provider='omr' AND format='musicxml' AND available=1"
    )
    cur.execute(query)
    reps = cur.fetchall()
    if args.limit:
        reps = reps[: args.limit]

    file_ids: dict[int, list[dict]] = {}
    for r in reps:
        m = re.search(r"/(\d+)/?$", str(r["download_url"] or ""))
        fid = int(m.group(1)) if m else None
        file_ids.setdefault(fid if fid else -1, []).append(r)

    cur2 = st.cursor()
    cur2.execute(
        "SELECT sl.file_id AS fid, sl.object_key FROM storage_locations sl "
        "WHERE sl.object_key LIKE '%.mxl'"
    )
    obj_by_file = {int(r["fid"]): str(r["object_key"]) for r in cur2.fetchall()}
    api.close()
    st.close()

    items = [
        (fid, obj_by_file.get(fid))
        for fid in file_ids
        if fid in obj_by_file
    ]
    missing_loc = sum(1 for fid in file_ids if fid not in obj_by_file)

    # Checkpoint: ficheros ya verificados en pasadas anteriores (file_id<TAB>reps<TAB>ok).
    stored: dict[int, tuple[int, bool]] = {}
    if args.checkpoint.exists():
        for line in args.checkpoint.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                stored[int(parts[0])] = (int(parts[1]), parts[2] == "1")

    ok_reps = sum(n for (n, ok) in stored.values() if ok)
    bad_reps = sum(n for (n, ok) in stored.values() if not ok)

    remaining = [it for it in items if it[0] not in stored]
    print(f"checkpoint: {len(stored)} ficheros ya verificados | restantes: {len(remaining)}", flush=True)

    seen_files: dict[int, dict] = {}
    processed_files = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for chunk in (remaining[i : i + 2000] for i in range(0, len(remaining), 2000)):
            if not chunk:
                continue
            results = pool.map(_process_files, [chunk])
            for rows in results:
                lines: list[str] = []
                for row in rows:
                    fid = int(row["file_id"])
                    seen_files[fid] = row
                    n = len(file_ids.get(fid, []))
                    if row["ok"]:
                        ok_reps += n
                    else:
                        bad_reps += n
                    lines.append(f"{fid}\t{n}\t{1 if row['ok'] else 0}")
                    processed_files += 1
                with args.checkpoint.open("a", encoding="utf-8") as fh:
                    fh.write("\n".join(lines) + "\n")
                print(f"  ... {processed_files} ficheros verificados (total reps OK={ok_reps}, malas={bad_reps})", flush=True)

    print("=" * 60)
    print(f"representaciones OMR evaluadas: {len(reps)} (nuevas {ok_reps + bad_reps - sum(n for n, _ in stored.values())})")
    print(f"ficheros únicos verificados: {len(stored) + len(seen_files)} | sin location (esta pasada): {missing_loc}")
    print(f"reps OK: {ok_reps} | reps rotas/incorrectas: {bad_reps}")
    bad_files = [v for v in seen_files.values() if not v["ok"]]
    for v in bad_files[:15]:
        print("  BROKEN file", v["file_id"], "|", v["reason"], "| size", v.get("size"))


if __name__ == "__main__":
    main()
