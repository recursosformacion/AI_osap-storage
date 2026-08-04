# osap-storage — Estructura

> Documento de arquitectura. Se mantiene sincronizado con el código. Edítalo cuando cambie la estructura, los módulos, el esquema de BD, la configuración o las capas.

## Visión general

`osap-storage` es un **mirror inteligente de ficheros individuales** (MusicXML) para OSAP.
No es un cliente de PDMX: convierte datasets externos (PDMX, en TARs) en un repositorio
propio mediante ingestión offline, y expone por HTTP únicamente "¿lo tengo? → sí → URL".

Se implementa con **arquitectura limpia** en Python 3.11+ / FastAPI / MariaDB / SQL nativo.

## Regla de dependencia

Las capas dependen hacia adentro. El dominio no conoce nada del mundo exterior.

```
api/  →  application/  →  domain/
infrastructure/  →  domain/
```

- `domain/` no importa de `application/`, `infrastructure/` ni `api/`.
- `application/` importa únicamente de `domain/`.
- `infrastructure/` y `api/` dependen de `domain/` y `application/` (composición root en `infrastructure/container.py`).

## Mapa de directorios

```
api/                    Capa HTTP (FastAPI). Sin lógica de negocio.
  main.py               create_app(), lifespan (conectar BD, migrar, bootstrap)
  dependencies.py       Resolver de dependencias (container → casos de uso)
  errors.py             Mapeo de excepciones de dominio → códigos HTTP
  schemas.py            Modelos Pydantic (request/response)
  routes/               health, providers, files, downloads, entries, archives

application/            Orquestación. Casos de uso + servicios de aplicación.
  use_cases/            register_file, start_download, get_file, list_files,
                        get_download_job, get_download_url, stream_file,
                        providers, import_pdmx, resolve_file, materialize_archive,
                        materialize_file, register_existing_file, verify_file,
                        delete_file, archives, statistics
  services/             file_publisher.py, tar_downloader.py

domain/                 Núcleo puro. Entidades, puertos, servicios, excepciones.
  entities/             file, storage_provider, storage_location, download_job,
                        archive, archive_entry
  ports/                repositories, storage (backend/registry), download,
                        hashing, tasks, archives (reader/factory), archive_repositories
  services/             file_registration, integrity, availability
  exceptions.py         DomainError y subtipos

infrastructure/         Implementaciones concretas (SQL, backends, adaptadores).
  config.py             Settings + carga de config.yaml (fuente YAML)
  bootstrap.py          Creación del proveedor por defecto según storage.backend
  container.py          Composition root: wiring de todo el grafo
  cli.py                Interfaz de línea de comandos (osap-storage)
  db/                   connection.py, migrate.py, migrations/*.sql
  repositories/         SQL nativo (aiomysql) de cada entidad
  providers/            registry + backends (local_disk, s3, google_drive, http_remote)
  archives/             tar_reader.py (lectura de TARs)
  importers/            pdmx_csv.py (parser del CSV de PDMX)
  downloaders/          httpx_downloader.py
  hashing/              hashlib_hasher.py
  tasks/                asyncio_scheduler.py

docs/                   Documentación (este fichero + funcionalidad.md)
tests/                  Tests unitarios/application con fakes en memoria
config.example.yaml     Fichero de configuración de referencia
```

## Dominio

### Entidades
- **`File`** — un fichero que **ya pertenece a OSAP** (materializado). Identificado por `sha256` (NOT NULL). Solo existe cuando el fichero ha sido publicado en un backend.
- **`StorageProvider`** — un backend físico (Filesystem, S3, Drive, servidor remoto). `provider_type` + `config`.
- **`StorageLocation`** — dónde está almacenada una copia física de un `File` en un proveedor (`file_id`, `provider_id`, `object_key`, `status`).
- **`DownloadJob`** — trabajo de descarga de una URL externa (V1; se mantiene por compatibilidad).
- **`Archive`** — un contenedor abstracto de un proveedor externo. `name` (único), `url`,
  `provider_id` (opcional), **`format`** (`tar`, `zip`, `directory`, ...), `local_path`,
  `status` (`imported|downloaded|materialized|failed`), `size`, `sha256`.
  **No conoce PDMX**: sirve para cualquier dataset (PDMX, IMSLP dump, ZIP, disco USB).
- **`ArchiveEntry`** — un fichero dentro de un `Archive`. `logical_id`, `relative_path`,
  `file_id` (NULL hasta materializar), `status` (`missing|ready|failed`). Único `(archive_id, relative_path)`.
- **`ImportSource`** — procedencia de un índice importado (`provider`, `version`, `csv_path`,
  `notes`, `imported_at`): PDMX v1/v2, OpenScore, IMSLP dump, etc.
- **`Statistics`** — instantánea del repositorio (`archives`, `entries`, `files`,
  `downloaded_tar`, `materialized`, `pending`, `bytes`).

Regla clave: **nunca se crean `File` "vacíos"**. Un `File` solo existe tras materializar (SHA256 calculado). El índice (import) solo crea `Archive` + `ArchiveEntry`.

### Puertos (interfaces)
- `FileRepository`, `StorageProviderRepository`, `StorageLocationRepository`, `DownloadJobRepository` (`domain/ports/repositories.py`).
- `ArchiveRepository`, `ArchiveEntryRepository` (`domain/ports/archive_repositories.py`).
- `ImportSourceRepository` (`import_source_repository.py`), `StatisticsRepository` (`statistics_repository.py`).
- `StorageBackend`, `StorageBackendRegistry` (`domain/ports/storage.py`).
- `FileDownloader` (`download.py`), `FileHasher` (`hashing.py`), `TaskScheduler` (`tasks.py`), `ArchiveReader`/`ArchiveReaderFactory` (`archives.py`).

### Servicios de dominio
- `FileRegistrationService` — validación de SHA256, deduplicación.
- `IntegrityService` — verificación de integridad.
- `AvailabilityService` — regla de disponibilidad (File con al menos una `StorageLocation` stored).

## Backends de almacenamiento

Todos implementan `StorageBackend` y se registran en `StorageBackendRegistry`.

| provider_type | Clase | Estado |
|---|---|---|
| `local_disk` (Filesystem) | `LocalDiskBackend` | **Implementado** (default) |
| `s3` (AWS/MinIO) | `S3Backend` | Requiere `boto3` (extra `[s3]`) |
| `google_drive` | `GoogleDriveBackend` | **Futuro** (stub, lanza `UnsupportedProvider`) |
| `http_remote` | `HttpRemoteBackend` | Mirror remoto de solo lectura |

El backend activo se elige por configuración (`storage.backend`). El dominio nunca contiene
código específico de un proveedor físico.

**Cómo añadir un backend:** crear la clase en `infrastructure/providers/`, implementar
`store`/`open_stream`/`url_for`/`delete`, y registrarla en `infrastructure/container.py`
(`registry.register(ProviderType.X, XBackend)`). No tocar el dominio.

## Configuración

Carga de configuración en `infrastructure/config.py`:

1. `config.yaml` (o la ruta en `OSAP_CONFIG`) — fuente única de configuración.
2. Variables de entorno y `.env` — **tienen prioridad** sobre el fichero (para secretos/DB).
3. Valores por defecto embebidos.

El backend por defecto se crea en arranque (`bootstrap.py`) según `storage.backend`.
Ver `config.example.yaml` para la referencia completa.

## Base de datos

MariaDB / MySQL 8. **SQL nativo** (sin ORM) mediante `aiomysql`. Migraciones versionadas
en `infrastructure/db/migrations/` aplicadas por `infrastructure/db/migrate.py`
(`schema_migrations` registra las aplicadas; idempotente).

- `001_init.sql` — `storage_providers`, `files`, `storage_locations`, `download_jobs`.
- `002_archives.sql` — `archives`, `archive_entries`.
- `003_import_sources_statistics.sql` — `archives.provider_id` + `archives.format`, `import_sources`, `statistics`.

Todas las PK son `BIGINT UNSIGNED AUTO_INCREMENT`. `files.sha256` es único.
`archives.name` es único. `archive_entries` tiene única `(archive_id, relative_path)`.

> Nota MySQL 8: la FK de `archive_entries.archive_id` requiere un índice dedicado
> (`idx_archive_entries_archive`); MySQL 8 no acepta la FK sobre un índice compuesto.

## CLI

`osap-storage` (`infrastructure/cli.py`), mismos casos de uso que la API.
Comandos: `import pdmx`, `materialize`, `materialize-file`, `register`, `resolve`,
`verify`, `delete`, `archives`, `stats`. Ver `docs/funcionalidad.md`.

## API

FastAPI. La API expone los casos de uso; nunca accede a MariaDB directamente desde una ruta
(usa los repositorios a través del container). Ver endpoints en `docs/funcionalidad.md`.

## Tests

`pytest` + `pytest-asyncio`. Repositorios/adaptadores con **fakes en memoria**
(`tests/fakes.py`), de modo que la lógica de dominio/aplicación se prueba sin BD.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
```
