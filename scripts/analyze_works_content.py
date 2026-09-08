"""Barrido offline de contenido de obras (sin R2): calcula y GUARDA, en paralelo.

Para cada `work` con su `.mxl` local (G:\\osap-storage, rutas vía
`storage_locations.object_key`):
  - calcula el `sha256` y tamaño reales y los persiste en `files`;
  - valida el MusicXML y guarda el "número mágico" (`works.music_digest`).

Uso (barrido completo, reanudable):
    .venv\\Scripts\\python.exe scripts/analyze_works_content.py --only-missing --workers 8
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import hashlib
import io
import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from infrastructure.config import Settings
from infrastructure.db.connection import Database

_DEFAULT_ROOT = Path("G:/osap-storage")


def _mxl_path(object_key: str, root: Path) -> Path:
    return root / object_key.lstrip("./").replace("\\", "/")


def _load_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _extract_xml(raw: bytes) -> bytes | None:
    if raw[:2] != b"PK":
        return raw
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            for name in names:
                if name.lower().endswith((".xml", ".musicxml")):
                    if name.lower().endswith("container.xml") or name.lower().startswith("meta-inf/"):
                        continue
                    return zf.read(name)
            if "META-INF/container.xml" in names:
                container = ElementTree.fromstring(zf.read("META-INF/container.xml"))
                for rootfile in container.iter():
                    if (rootfile.tag or "").rsplit("}", 1)[-1] == "rootfile":
                        full = rootfile.get("full-path")
                        if full:
                            return zf.read(full)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        return None
    return None


def _validate(raw: bytes) -> tuple[bool, str | None]:
    xml_bytes = _extract_xml(raw)
    if xml_bytes is None:
        return False, "sin XML legible"
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        return False, f"XML inválido: {exc}"
    tag = (root.tag or "").rsplit("}", 1)[-1]
    if tag not in ("score-partwise", "score-timewise"):
        return False, f"raíz no partiture: {tag}"
    if not any((el.tag or "").endswith("note") for el in root.iter()):
        return False, "sin notas"
    return True, None


def _music_digest(raw: bytes) -> str | None:
    xml_bytes = _extract_xml(raw)
    if xml_bytes is None:
        return None
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return None
    parts: list[str] = []
    for el in root.iter():
        if not (el.tag or "").endswith("note"):
            continue
        step = octave = duration = voice = "-"
        for child in el:
            ctag = (child.tag or "").rsplit("}", 1)[-1]
            if ctag == "pitch":
                for pc in child:
                    p = (pc.tag or "").rsplit("}", 1)[-1]
                    if p == "step" and pc.text:
                        step = pc.text
                    elif p == "octave" and pc.text:
                        octave = pc.text
            elif ctag == "duration" and child.text:
                duration = child.text
            elif ctag == "voice" and child.text:
                voice = child.text
        parts.append(f"{step}{octave}|{duration}|{voice}")
    if not parts:
        return None
    return hashlib.md5(";".join(parts).encode("utf-8")).hexdigest()


def _process_batch(
    batch: list[tuple[int, str]], key_by_cid: dict[str, tuple[str, int | None]], root: str
) -> list[dict]:
    """Procesa un lote (procesos): devuelve filas para actualizar la BD por file_id (PK)."""
    out: list[dict] = []
    for work_id, work_key in batch:
        loc = key_by_cid.get(f"{work_key}.mxl")
        if loc is None:
            continue
        object_key, file_id = loc
        if file_id is None:
            continue
        raw = _load_bytes(_mxl_path(object_key, Path(root)))
        if raw is None:
            continue
        ok, _reason = _validate(raw)
        digest = _music_digest(raw) if ok else None
        out.append(
            {
                "work_id": work_id,
                "file_id": file_id,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
                "digest": digest,
                "valid": ok,
            }
        )
    return out


async def scan(limit: int | None, only_missing: bool, root: Path, workers: int, batch: int) -> None:
    db = Database(Settings())
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT object_key, file_id FROM storage_locations WHERE object_key LIKE '%.mxl'"
        )
        key_by_cid = {
            Path(str(r["object_key"]).lstrip("./")).name: (
                str(r["object_key"]),
                int(r["file_id"]) if r["file_id"] is not None else None,
            )
            for r in await cur.fetchall()
        }
        query = "SELECT id, work_key FROM works"
        params: list[object] = []
        if only_missing:
            query += " WHERE music_digest IS NULL"
        query += " ORDER BY id"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        await cur.execute(query, params)
        works = [(int(w["id"]), str(w["work_key"] or "")) for w in await cur.fetchall()]

    total = len(works)
    chunks = [works[i : i + batch] for i in range(0, total, batch)]
    print(f"pendientes: {total} (workers={workers}, lote={batch})", flush=True)

    processed = 0
    updated_sha = 0
    updated_digest = 0
    missing = 0
    invalid = 0
    loop = asyncio.get_event_loop()
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        async with db.connection() as conn, conn.cursor() as cur:
            for chunk in chunks:
                rows = await loop.run_in_executor(
                    pool, _process_batch, chunk, key_by_cid, str(root)
                )
                missing += len(chunk) - len(rows)
                if rows:
                    await cur.executemany(
                        "UPDATE files SET sha256 = %s, size_bytes = %s WHERE id = %s",
                        [(r["sha256"], r["size"], r["file_id"]) for r in rows],
                    )
                    await cur.executemany(
                        "UPDATE works SET music_digest = %s WHERE id = %s",
                        [(r["digest"], r["work_id"]) for r in rows],
                    )
                    await conn.commit()
                    updated_sha += len(rows)
                    updated_digest += sum(1 for r in rows if r["digest"] is not None)
                    invalid += sum(1 for r in rows if not r["valid"])
                processed += len(chunk)
                print(f"  ... {processed}/{total} (sha={updated_sha}, digest={updated_digest})", flush=True)

    print("=" * 60)
    print(f"procesadas: {processed} | sin path/fichero: {missing}")
    print(f"sha actualizado: {updated_sha} | music_digest guardado: {updated_digest} | inválidos: {invalid}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="limitar nº de obras (pruebas)")
    parser.add_argument("--only-missing", action="store_true", help="solo obras sin music_digest")
    parser.add_argument("--root", type=Path, default=_DEFAULT_ROOT)
    parser.add_argument("--workers", type=int, default=max(4, os.cpu_count() or 4))
    parser.add_argument("--batch", type=int, default=2000)
    args = parser.parse_args()
    asyncio.run(scan(args.limit, args.only_missing, args.root, args.workers, args.batch))


if __name__ == "__main__":
    main()
