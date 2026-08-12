from __future__ import annotations

import argparse
import asyncio
import csv
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from application.use_cases.import_pdmx import PdmxImportResult
from application.use_cases.materialize_archive import MaterializeArchiveCommand
from application.use_cases.materialize_file import MaterializeFileCommand
from application.use_cases.populate_composers import PopulateComposers
from application.use_cases.register_existing_file import RegisterExistingFileCommand
from application.use_cases.register_resources import RegisterMirrorResourcesCommand
from domain.entities.import_source import ImportSource

from infrastructure.config import Settings
from infrastructure.container import Container, build_container
from infrastructure.doctor import run_doctor
from infrastructure.importers.pdmx_csv import read_pdmx_csv
from infrastructure.verification import verify_mirror


def _dumps(obj: Any) -> str:
    if isinstance(obj, PdmxImportResult):
        return json.dumps(asdict(obj), ensure_ascii=False)
    if is_dataclass(obj):
        return json.dumps(asdict(obj), ensure_ascii=False, default=str)
    return json.dumps(obj, ensure_ascii=False, default=str)


_COMPOSER_COLUMNS = ("composer_name", "composer", "artist_name", "artist")


def _read_composer_names(path: str) -> list[str]:
    """Lee los nombres de compositor de un CSV (detectando la columna)."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        lowered = [h.strip().lower() for h in header]
        column = next((header[lowered.index(c)] for c in _COMPOSER_COLUMNS if c in lowered), None)
        if column is None:
            raise ValueError(f"CSV sin columna de compositor; encontradas: {', '.join(header)}")
        return [record[column] for record in reader if record.get(column)]


def _cmd_populate_composers(args: argparse.Namespace, container: Container):
    csv_path = args.csv or container.settings.pdmx_source_csv
    if not csv_path:
        raise ValueError("no CSV: indica --csv o providers.pdmx.source.csv en config")
    names = _read_composer_names(csv_path)
    return PopulateComposers(container.composer_repo).execute(names, provider=args.provider)


async def _cmd_backfill_creation_evidence(args: argparse.Namespace, container: Container):
    return {"created": await container.composer_repo.backfill_creation_evidence(provider=args.provider)}


async def _cmd_classify_composers(args: argparse.Namespace, container: Container):
    return await container.classify_composers.execute()


async def _cmd_clean_composer_names(args: argparse.Namespace, container: Container):
    return await container.clean_composer_names.execute()


async def _cmd_prune_composers(args: argparse.Namespace, container: Container):
    return {"removed": await container.prune_composers.execute()}


async def _cmd_musicbrainz_enrich(args: argparse.Namespace, container: Container):
    from application.use_cases.musicbrainz_enrich import EnrichComposersMusicBrainz

    from infrastructure.repositories.sql_musicbrainz_cache_repository import (
        SqlMusicBrainzCacheRepository,
    )
    from infrastructure.services.musicbrainz_client import (
        CachedMusicBrainzClient,
        MusicBrainzClient,
    )

    mb = CachedMusicBrainzClient(MusicBrainzClient(), SqlMusicBrainzCacheRepository(container.db))
    return await EnrichComposersMusicBrainz(container.composer_repo, mb).execute(limit=args.limit)


async def _cmd_backfill_composer_ids(args: argparse.Namespace, container: Container):
    from domain.entities.composer import UNKNOWN_COMPOSER_ID
    from domain.services.composer_quality import extract_composer_name
    from domain.services.composer_resolver import ComposerResolver

    resolver = ComposerResolver(container.composer_repo)
    await container.composer_repo.ensure_unknown_composer()
    updated = 0
    scanned = 0
    offset = 0
    limit = 500
    extract_cache: dict[str | None, str | None] = {}
    while True:
        works = await container.work_repo.list_all(limit=limit, offset=offset)
        if not works:
            break
        # Extrae el nombre del compositor con el MISMO algoritmo de populate (heurística+NER),
        # con caché por texto bruto (los nombres se repiten en miles de obras).
        extracted = []
        for w in works:
            if w.composer not in extract_cache:
                extract_cache[w.composer] = extract_composer_name(w.composer)
            extracted.append(extract_cache[w.composer])
        resolved = await resolver.resolve_many(extracted)
        pending = []
        for w, name in zip(works, extracted, strict=True):
            scanned += 1
            r = resolved.get(name)
            new_id = r[0] if r else UNKNOWN_COMPOSER_ID
            if w.composer_id != new_id:
                w.composer_id = new_id
                pending.append(w)
        for w in pending:
            await container.work_repo.update(w)
        updated += len(pending)
        offset += limit
    return {"scanned": scanned, "updated": updated}


async def _cmd_recompute_statistics(args: argparse.Namespace, container: Container):
    return await container.refresh_voting_statistics.execute()


async def _cmd_register_external_work(args: argparse.Namespace, container: Container):
    from application.use_cases.external_works import RegisterExternalWork

    work = await RegisterExternalWork(container.work_repo).execute(
        reference=args.reference,
        provider=args.provider,
        composer=args.composer,
        title=args.title,
    )
    return {
        "work_id": work.id,
        "work_key": work.work_key,
        "relative_path": work.relative_path,
        "tags": work.tags,
    }


def _cmd_import_pdmx(args: argparse.Namespace, container: Container):
    rows = read_pdmx_csv(
        args.csv,
        relative_path_col=args.relative_path_col,
        archive_name_col=args.archive_name_col,
        archive_name=args.archive_name,
        archive_url_col=args.archive_url_col,
        archive_url=args.archive_url,
        logical_id_col=args.logical_id_col,
        composer_col=args.composer_col,
        title_col=args.title_col,
    )
    source = ImportSource(provider="pdmx", version=args.version, csv_path=args.csv, notes=args.notes)
    return container.import_pdmx.import_rows(rows, source=source)


def _cmd_materialize(args: argparse.Namespace, container: Container):
    return container.materialize_archive.execute(
        MaterializeArchiveCommand(
            archive_id=args.archive_id,
            provider_id=args.provider,
            local_path=args.local_path,
            download=args.download,
            keep_tar=not args.no_keep_tar,
        )
    )


def _cmd_materialize_file(args: argparse.Namespace, container: Container):
    return container.materialize_file.execute(
        MaterializeFileCommand(
            entry_id=args.entry,
            logical_id=args.logical_id,
            relative_path=args.relative_path,
            provider_id=args.provider,
            download=not args.no_download,
            keep_tar=not args.no_keep_tar,
        )
    )


def _cmd_stats(args: argparse.Namespace, container: Container):
    return container.get_statistics.execute(refresh=args.refresh)


def _cmd_register_resources(args: argparse.Namespace, container: Container):
    return container.register_resources.execute(
        RegisterMirrorResourcesCommand(archive_id=args.archive_id, provider_id=args.provider)
    )


def _cmd_register_works(args: argparse.Namespace, container: Container):
    return container.build_works.execute()


async def _cmd_enrich_metadata(args: argparse.Namespace, container: Container):
    from infrastructure.enrichment.metadata import build_enrichment, extract_metadata, load_csv_index
    from infrastructure.enrichment.metadata_source import LocalMetadataReader, R2MetadataReader

    csv_path = args.csv or container.settings.pdmx_source_csv
    if not csv_path:
        raise ValueError("no CSV: indica --csv o providers.pdmx.source.csv")

    reader = (
        R2MetadataReader(container.settings)
        if args.source == "r2"
        else LocalMetadataReader(args.metadata_dir)
    )

    csv_index = load_csv_index(csv_path)
    processed = updated = errors = 0
    error_list: list[dict] = []
    offset = 0
    limit = 1000
    while True:
        works = await container.work_repo.list_all(limit=limit, offset=offset)
        if not works:
            break
        for w in works:
            processed += 1
            csv_meta = csv_index.get(w.work_key)
            json_meta = None
            if csv_meta and csv_meta.get("metadata_path"):
                try:
                    data = reader.read(csv_meta["metadata_path"])
                    json_meta = extract_metadata(data)
                except Exception as exc:
                    error_list.append({"work_key": w.work_key, "error": f"json: {exc}"})
                    errors += 1
                    continue
            if csv_meta is None and json_meta is None:
                continue
            try:
                await container.enrich_work.execute(w, build_enrichment(csv_meta, json_meta))
                updated += 1
            except Exception as exc:
                error_list.append({"work_key": w.work_key, "error": str(exc)})
                errors += 1
        offset += limit
    return {"processed": processed, "updated": updated, "errors": errors, "error_list": error_list[:30]}


async def _cmd_verify_mirror(args: argparse.Namespace, container: Container):
    csv_path = args.csv or container.settings.pdmx_source_csv
    if not csv_path:
        raise ValueError("no se encontró el CSV: indica --csv o providers.pdmx.source.csv en config")
    report = await verify_mirror(
        container.archive_repo, container.archive_entry_repo, csv_path, args.archive
    )
    for label, value in (
        ("CSV", report.csv),
        ("ArchiveEntry", report.archive_entries),
        ("MusicXML", report.musicxml),
        ("Missing", report.missing),
        ("Extra", report.extra),
    ):
        print(f"{label:<14}{value}")
    print("Mirror OK" if report.ok else "Mirror ERROR")
    return None


def _row(label: str, value: str) -> str:
    return f"{label}{'.' * max(0, 17 - len(label))}{value}"


async def _cmd_doctor(args: argparse.Namespace, container: Container):
    csv_path = args.csv or container.settings.pdmx_source_csv
    report = await run_doctor(container, csv_path, args.archive, check_links=args.links)

    def status(ok: bool) -> str:
        return "OK" if ok else "ERROR"

    print(_row("Mirror", status(report.mirror_ok)))
    print(_row("Database", status(report.database_ok)))
    print(_row("Storage", status(report.storage_ok)))
    print(_row("Providers", str(report.providers)))
    print(_row("Archives", str(report.archives)))
    print(_row("ArchiveEntries", str(report.archive_entries)))
    print(_row("Files", str(report.files)))
    print(_row("StorageLocations", str(report.storage_locations)))
    if args.links:
        print(_row("Links", f"{report.links_checked} comprobados, {report.links_missing} faltan"))
        for sample in report.links_samples:
            print("  falta:", sample)
    print()
    print("Everything is OK" if report.ok else "PROBLEMS FOUND")
    if not report.mirror_ok:
        print("Mirror:", report.mirror_detail)
    if not report.storage_ok:
        print("Storage:", report.storage_detail)
    return None


def _cmd_register(args: argparse.Namespace, container: Container):
    return container.register_existing_file.execute(
        RegisterExistingFileCommand(path=args.path, name=args.name, provider_id=args.provider)
    )


def _cmd_resolve(args: argparse.Namespace, container: Container):
    return container.resolve_file.execute(relative_path=args.relative_path, logical_id=args.logical_id)


def _cmd_verify(args: argparse.Namespace, container: Container):
    return container.verify_file.execute(args.file_id)


def _cmd_delete(args: argparse.Namespace, container: Container):
    return container.delete_file.execute(args.file_id)


def _cmd_list_archives(args: argparse.Namespace, container: Container):
    return container.list_archives.execute(limit=args.limit, offset=args.offset)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="osap-storage")
    sub = parser.add_subparsers(dest="command", required=True)

    importer = sub.add_parser("import", help="Importar índices")
    imp_sub = importer.add_subparsers(dest="subcommand", required=True)
    pdmx = imp_sub.add_parser("pdmx", help="Construir índice PDMX desde un CSV (sin descargar nada)")
    pdmx.add_argument("csv")
    pdmx.add_argument("--relative-path-col", default=None)
    pdmx.add_argument("--archive-name-col", default=None)
    pdmx.add_argument("--archive-name", default=None, help="Nombre del archive (constante, p.ej. mxl.tar.gz)")
    pdmx.add_argument("--archive-url-col", default=None)
    pdmx.add_argument("--archive-url", default=None, help="URL del archive (constante)")
    pdmx.add_argument("--logical-id-col", default=None)
    pdmx.add_argument("--composer-col", default=None, help="Columna del compositor")
    pdmx.add_argument("--title-col", default=None, help="Columna del título")
    pdmx.add_argument("--version", default=None, help="Versión del dataset importado")
    pdmx.add_argument("--notes", default=None)
    pdmx.set_defaults(handler=_cmd_import_pdmx)

    materialize = sub.add_parser("materialize", help="Descomprimir un archive, registrar y publicar sus ficheros")
    materialize.add_argument("archive_id", type=int)
    materialize.add_argument("--provider", type=int, default=None)
    materialize.add_argument("--local-path", default=None)
    materialize.add_argument(
        "--download", action="store_true", help="Descargar el TAR desde archive.url a la caché si no existe"
    )
    materialize.add_argument(
        "--no-keep-tar", action="store_true", help="Eliminar el TAR de la caché tras materializar (si se descargó)"
    )
    materialize.set_defaults(handler=_cmd_materialize)

    register = sub.add_parser("register", help="Registrar un fichero ya existente en disco")
    register.add_argument("path")
    register.add_argument("--name", default=None)
    register.add_argument("--provider", type=int, default=None)
    register.set_defaults(handler=_cmd_register)

    resolve = sub.add_parser("resolve", help="Resolver 'lo tengo / no lo tengo'")
    resolve.add_argument("--relative-path", default=None)
    resolve.add_argument("--logical-id", default=None)
    resolve.set_defaults(handler=_cmd_resolve)

    verify = sub.add_parser("verify", help="Verificar integridad (SHA256) de un fichero")
    verify.add_argument("file_id", type=int)
    verify.set_defaults(handler=_cmd_verify)

    delete = sub.add_parser("delete", help="Borrar un fichero y sus copias físicas")
    delete.add_argument("file_id", type=int)
    delete.set_defaults(handler=_cmd_delete)

    archives = sub.add_parser("archives", help="Listar archives")
    archives.add_argument("--limit", type=int, default=100)
    archives.add_argument("--offset", type=int, default=0)
    archives.set_defaults(handler=_cmd_list_archives)

    materialize_file = sub.add_parser(
        "materialize-file", help="Materializar un único ArchiveEntry (lógico_id → File)"
    )
    materialize_file.add_argument("--entry", type=int, default=None, help="ID de ArchiveEntry")
    materialize_file.add_argument("--logical-id", default=None)
    materialize_file.add_argument("--relative-path", default=None)
    materialize_file.add_argument("--provider", type=int, default=None)
    materialize_file.add_argument("--no-download", action="store_true", help="No descargar el TAR")
    materialize_file.add_argument(
        "--no-keep-tar", action="store_true", help="Eliminar el TAR de la caché tras materializar"
    )
    materialize_file.set_defaults(handler=_cmd_materialize_file)

    stats = sub.add_parser("stats", help="Ver/actualizar estadísticas del repositorio")
    stats.add_argument("--refresh", action="store_true", help="Recalcular la instantánea")
    stats.set_defaults(handler=_cmd_stats)

    verify = sub.add_parser(
        "verify-mirror", help="Comprobar consistencia del mirror (CSV vs índice vs ficheros)"
    )
    verify.add_argument("--csv", default=None, help="Ruta al PDMX.csv (por defecto: config)")
    verify.add_argument("--archive", default="mxl.tar.gz", help="Nombre del archive (default mxl.tar.gz)")
    verify.set_defaults(handler=_cmd_verify_mirror)

    doctor = sub.add_parser("doctor", help="Diagnóstico del sistema (git fsck)")
    doctor.add_argument("--csv", default=None, help="Ruta al PDMX.csv (por defecto: config)")
    doctor.add_argument("--archive", default="mxl.tar.gz", help="Nombre del archive (default mxl.tar.gz)")
    doctor.add_argument(
        "--links",
        action="store_true",
        help="Comprobar que cada StorageLocation existe físicamente en el repositorio",
    )
    doctor.set_defaults(handler=_cmd_doctor)

    register_resources = sub.add_parser(
        "register-resources",
        help="Registrar File + StorageLocation de un archive (mirror como primer proveedor, sin copiar)",
    )
    register_resources.add_argument("archive_id", type=int)
    register_resources.add_argument("--provider", type=int, default=None)
    register_resources.set_defaults(handler=_cmd_register_resources)

    register_works = sub.add_parser(
        "register-works",
        help="Construir las Works a partir de los recursos (por hash PDMX)",
    )
    register_works.set_defaults(handler=_cmd_register_works)

    enrich = sub.add_parser(
        "enrich-metadata",
        help="Enriquecer las Works con metadata de PDMX (CSV + JSON MuseScore)",
    )
    enrich.add_argument("--csv", default=None, help="Ruta al PDMX.csv (por defecto: config)")
    enrich.add_argument("--metadata-dir", default=r"G:\osap-storage",
                        help="Raíz del mirror con metadata/ (fuente local)")
    enrich.add_argument("--source", choices=["local", "r2"], default="local",
                        help="De dónde leer los JSON (local=G:, r2=Cloudflare R2)")
    enrich.set_defaults(handler=_cmd_enrich_metadata)

    populate = sub.add_parser(
        "populate-composers",
        help="Poblar composers/composer_aliases desde un CSV con columna de compositor",
    )
    populate.add_argument("csv", nargs="?", default=None, help="Ruta al CSV (por defecto: config)")
    populate.add_argument("--provider", default="pdmx",
                          help="Proveedor/origen para registrar evidencia de creación")
    populate.set_defaults(handler=_cmd_populate_composers)

    backfill_ev = sub.add_parser(
        "backfill-creation-evidence",
        help="Crear evidencia de creación para compositores activos que aún no la tienen",
    )
    backfill_ev.add_argument("--provider", default="pdmx", help="Origen a registrar")
    backfill_ev.set_defaults(handler=_cmd_backfill_creation_evidence)

    classify = sub.add_parser(
        "classify-composers",
        help="Clasificar heurísticamente los compositores pendientes como correct/false",
    )
    classify.set_defaults(handler=_cmd_classify_composers)

    clean = sub.add_parser(
        "clean-composer-names",
        help="Limpiar los nombres de compositor y fusionar colisiones",
    )
    clean.set_defaults(handler=_cmd_clean_composer_names)

    prune = sub.add_parser(
        "prune-composers",
        help="Eliminar compositores activos sin ninguna obra (fantasmas)",
    )
    prune.set_defaults(handler=_cmd_prune_composers)

    mb = sub.add_parser(
        "musicbrainz-enrich",
        help="Validar/canonicalizar/fusionar compositores con MusicBrainz (respeta 1 req/s)",
    )
    mb.add_argument("--limit", type=int, default=50, help="Nº de compositores a procesar")
    mb.set_defaults(handler=_cmd_musicbrainz_enrich)

    backfill = sub.add_parser(
        "backfill-composer-ids",
        help="Rellenar works.composer_id resolviendo works.composer contra los alias",
    )
    backfill.set_defaults(handler=_cmd_backfill_composer_ids)

    recompute = sub.add_parser(
        "recompute-statistics",
        help="Recalcular las estadísticas de votación (works y compositores). Idempotente.",
    )
    recompute.set_defaults(handler=_cmd_recompute_statistics)

    external = sub.add_parser(
        "register-external-work",
        help="Registrar una obra externa sin fichero local (conserva referencia y procedencia)",
    )
    external.add_argument("--reference", required=True, help="Referencia proporcionada por el proveedor")
    external.add_argument("--provider", required=True, help="Nombre del proveedor/directorio externo")
    external.add_argument("--composer", default=None, help="Compositor (opcional)")
    external.add_argument("--title", default=None, help="Título (opcional)")
    external.set_defaults(handler=_cmd_register_external_work)

    return parser


async def _run(args: argparse.Namespace, container: Container) -> None:
    await container.db.connect()
    try:
        result = await args.handler(args, container)
        if result is not None:
            print(_dumps(result))
    finally:
        await container.db.close()


def main() -> None:
    args = build_parser().parse_args()
    container = build_container(Settings())  # type: ignore[call-arg]
    asyncio.run(_run(args, container))


if __name__ == "__main__":
    main()
