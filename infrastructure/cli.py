from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from application.use_cases.import_pdmx import PdmxImportResult
from application.use_cases.materialize_archive import MaterializeArchiveCommand
from application.use_cases.materialize_file import MaterializeFileCommand
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
    container = build_container(Settings())
    asyncio.run(_run(args, container))


if __name__ == "__main__":
    main()
