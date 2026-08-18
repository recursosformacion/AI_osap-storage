#!/usr/bin/env python
"""Ingerir los snapshots JSON (`data/authority/*.json`) en `authority_identifiers`.

Idempotente. No consulta fuentes externas ni decide identificadores: solo materializa lo
ya obtenido en storage. Los JSON se conservan como evidencia/procedencia.

Uso:
    python scripts/ingest_authority.py --archive /ruta/data/authority
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from infrastructure.config import Settings
from infrastructure.db.connection import Database
from infrastructure.repositories.sql_authority_identifier_repository import SqlAuthorityIdentifierRepository
from infrastructure.services.authority_ingestor import AuthoritySnapshotIngestor


def _load(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


async def _run(archive: Path) -> int:
    db = Database(Settings())  # type: ignore[call-arg]
    repo = SqlAuthorityIdentifierRepository(db)
    ingestor = AuthoritySnapshotIngestor(repo)
    composers = _load(archive / "composers.json")
    works = _load(archive / "works.json")
    rc = await ingestor.ingest_composers(composers)
    rw = await ingestor.ingest_works(works)
    print("compositores:", rc)
    print("obras       :", rw)
    return 0


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("data/authority"))
    args = parser.parse_args()
    return asyncio.run(_run(args.archive))


if __name__ == "__main__":
    sys.exit(main())
