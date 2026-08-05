# osap-storage — Funcionalidad

> Documento funcional. Se mantiene sincronizado con el código. Edítalo cuando cambien
> comandos, endpoints, config o comportamiento.

## Filosofía

`osap-storage` **no descarga ficheros individuales bajo demanda desde PDMX**.
PDMX distribuye los MusicXML dentro de TARs de muchos GB; abrir un TAR no puede formar
parte del tiempo de respuesta de un usuario.

Por tanto es un **mirror inteligente de MusicXML individuales**: un repositorio propio
donde, cuando un usuario pide una obra, el fichero ya está publicado en el backend.

Hay **dos procesos completamente separados**:

| | Ingestión (offline) | Servicio (online) |
|---|---|---|
| Naturaleza | Administrativa, dura horas/días, sin usuarios | Peticiones de usuarios, responde en segundos |
| Acceso a externo | Sí (PDMX/Zenodo/TARs) | Nunca |
| Operaciones | Importar índice, materializar | "¿Lo tengo?" → URL |

El servicio nunca abre un TAR ni descarga datasets: solo consulta el repositorio propio.

## Modelo conceptual

- **`Archive`** — un contenedor abstracto de un proveedor externo (`tar`, `zip`, `directory`...).
  No conoce PDMX: sirve para cualquier dataset futuro.
- **`ArchiveEntry`** — un fichero contenido dentro del `Archive`.
- **`File`** — un **recurso conocido** por el sistema, no necesariamente un fichero físico propio.
  El `sha256` es opcional (NULL en el mirror; no se calcula).
- **`StorageLocation`** — dónde está accesible un `File`. En el mirror apunta directamente a la
  ruta dentro del mirror (`object_key` = relative_path), **sin copiar ni hashear nada**.
- **`ImportSource`** — procedencia de cada índice importado (PDMX v1/v2, OpenScore, IMSLP dump...).

El mirror **es el primer proveedor de almacenamiento** de osap-storage. La importación crea el
índice (`Archive` + `ArchiveEntry`) y el registro de recursos crea el `File` + `StorageLocation`
correspondiente apuntando al mirror. Más adelante un mismo `File` podrá tener más
`StorageLocation`s (S3, CDN, Drive...), pero el mirror siempre será la primera ubicación física.

## Ingestión (offline)

El contrato es simple:

```
IMPORT
  ↓
descarga mirror
  ↓
extrae mirror
  ↓
importa índice (PDMX.csv)
  ↓
SERVICIO LISTO
```

No hay fase de "materialización masiva": mientras el almacenamiento es únicamente el mirror
de PDMX, los `ArchiveEntry` se sirven **directamente desde el mirror extraído**. El proceso de
registro + SHA256 + `File`/`StorageLocation` solo tiene sentido en una V2 con MusicXML subidos
por usuarios (contenido propio, no mirror oficial).

### `osap-storage import pdmx <csv> ...`

Construye el índice **sin descargar nada**: registra `Archive`s (deduplicados por nombre)
y `ArchiveEntry`s (estado `missing`). Idempotente (`INSERT IGNORE`).
Registra además un `ImportSource` con la procedencia del CSV (`--version` / `--notes`).

### `osap-storage doctor [--csv ...] [--archive mxl.tar.gz] [--links]`

Diagnóstico del sistema (equivalente a `git fsck`): comprueba la conexión a la BD, el backend
de almacenamiento y la consistencia del mirror, y muestra los contadores (Providers, Archives,
ArchiveEntries, Files, StorageLocations). Termina con `Everything is OK` si todo está correcto.

Con `--links` comprueba además que **cada `StorageLocation` existe físicamente** en su proveedor
(enlace índice → fichero) y lista las rutas faltantes.

### `osap-storage register-resources <archive_id> [--provider N]`

Registra el `File` + `StorageLocation` de cada `ArchiveEntry` del mirror: `StorageLocation.object_key`
= relative_path y el proveedor es el mirror (primer proveedor). No copia nada ni calcula SHA256.
Idempotente (ignora entradas que ya tienen `file_id`).

### `osap-storage verify-mirror [--csv ...] [--archive mxl.tar.gz]`

Comprueba la consistencia del mirror: compara el número de registros del CSV, los `ArchiveEntry`
del índice y los ficheros `.mxl` reales en disco, y reporta `missing` / `extra`. Termina con
`Mirror OK` si todo coincide. Es la herramienta de referencia para saber "exactamente qué tienes".

### `osap-storage materialize <archive_id> [--provider N] [--local-path ...] [--download] [--no-keep-tar]`

Descomprime un TAR completo, y por cada entrada: extrae → calcula SHA256 → registra `File`
(dedupe por SHA256) → publica en el backend → crea `StorageLocation` → marca `ready`.

- `--download`: si el TAR no está disponible, lo descarga desde `archive.url` a `temp_dir`
  (proceso offline; reutiliza el TAR si ya está).
- `--no-keep-tar`: elimina el TAR tras materializar (solo si se descargó en esta ejecución).
- `--local-path`: usa un TAR ya disponible en disco sin descargarlo.

Nota: este flujo es una herramienta offline opcional de ingesta de datasets en TAR. El mirror
de PDMX ya construido no lo necesita: sus `StorageLocation` apuntan directamente al repositorio.

Al terminar el `Archive` pasa a `materialized` (o `failed` si hubo errores).

### `osap-storage materialize-file --logical-id <key> | --relative-path <path> | --entry <id> [--provider N] [--no-download] [--no-keep-tar]`

Materializa **un único ArchiveEntry** (el flujo central del mirror):
`logical_id → buscar ArchiveEntry → ¿está el TAR? (no → descargar) → extraer ese fichero →
SHA256 → File → StorageLocation → READY`. Proceso offline/administrativo, no forma parte del
tiempo de respuesta de un usuario.

### `osap-storage stats [--refresh]`

Muestra o recalcula las estadísticas del repositorio (mirror): TARs descargados,
MusicXML disponibles, pendientes, bytes ocupados, errores.

## Servicio (online)

### `osap-storage resolve --relative-path <path> | --logical-id <key>`

Responde "¿lo tengo?": devuelve `found`, `archive_name`, `status`, `available`, `file_id`.
`available=true` solo si la entrada está `ready` y tiene `file_id`.

**Con `repository.cloudflare_r2.serve_directly: true`**: si la entrada existe en el índice, devuelve
`available=true` y una URL directa al CDN (`https://cdn.openmusicrepository.com/pdmx/mxl/...`),
sin necesidad de materializar ni servir el fichero desde el propio servidor.

### API

El servidor solo ofrece: "¿Lo tengo?" → URL. No hay lógica de TAR durante una petición HTTP.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/v1/health` | Estado y conexión a BD |
| GET | `/api/v1/entries/resolve?relative_path=&logical_id=` | Resolver (found/available/file_id/url) |
| GET | `/api/v1/files` | Listar ficheros (con disponibilidad) |
| POST | `/api/v1/files` | Registrar un fichero (sha256 + nombre) |
| GET | `/api/v1/files/{id}` | Detalle + disponibilidad |
| GET | `/api/v1/files/{id}/content` | Descargar el fichero (streaming) |
| GET | `/api/v1/files/{id}/url` | URL de descarga |
| POST | `/api/v1/files/{id}/verify` | Recalcular SHA256 de las copias almacenadas |
| DELETE | `/api/v1/files/{id}` | Borrar el fichero y sus copias físicas |
| POST | `/api/v1/files/{id}/downloads` | Job de descarga desde URL externa (V1) |
| GET | `/api/v1/downloads/{job_id}` | Estado de un job de descarga |
| GET/POST | `/api/v1/providers` | Listar / crear proveedores |
| GET | `/api/v1/archives` | Listar archives |
| GET | `/api/v1/archives/{id}` | Detalle de un archive |
| GET | `/api/v1/statistics?refresh=` | Estadísticas del repositorio |

## Operaciones locales (Fase 1)

- **`register <path>`** — registra un fichero ya existente en disco: calcula SHA256,
  deduplica y lo publica en el backend (crea `File` + `StorageLocation`).
- **`verify <file_id>`** — recomprueba el SHA256 de cada copia almacenada.
- **`delete <file_id>`** — elimina las copias físicas y el registro.

## Configuración

Fichero único y externo `config.yaml` (ruta por defecto en la raíz, o `OSAP_CONFIG`).
`config.py` solo define el esquema: **sin valores en código**. `config.yaml` está en
`.gitignore` (contiene credenciales). Plantillas en el repo: `config.example.yaml`
(generica) y `config.production.example.yaml` (producción). Producción (91.134.255.134)
tiene su propio `config.yaml` y solo se modifica al cerrar una versión. Referencia:

```yaml
db:
  host, port, user, password, name, pool_size   # Conexión a MariaDB/MySQL

http:
  host, port, public_base_url

temp_dir: /tmp

bootstrap:
  create_default_provider: true

repository:
  provider: local          # desarrollo (Filesystem) | cloudflare_r2 (producción)
  local:
    root: data/files
  cloudflare_r2:
    bucket: pdmx
    endpoint: https://ACCOUNT.r2.cloudflarestorage.com
    account_id: ACCOUNT
    access_key: ...
    secret_key: ...
    public_url: https://cdn.openmusicrepository.com
    path_prefix: pdmx
    serve_directly: true

providers:
  pdmx:
    source:
      csv: data/pdmx/pdmx.csv
      zenodo: { base_url: https://zenodo.org/records/XXXX }
```

El repositorio activo se elige con `repository.provider`; el proveedor por defecto se crea al
arrancar si no existe ninguno (`bootstrap.py`). En producción el repositorio es **Cloudflare R2**
(con `serve_directly`, el resolver devuelve URLs directas al CDN).

## Versiones

**V1 — CERRADA** (2026-08). Desplegada en producción (`storage.openmusicrepository.com`).

- Modelo de datos (archives/entries + files/locations + import_sources + statistics).
- Importador de índice PDMX offline (registra `ImportSource`).
- Repositorio oficial en Cloudflare R2 con CDN público (254,035 MusicXML + PDF/MIDI).
- Resolver ("lo tengo / no lo tengo") + URL de descarga.
- Buscador web (compositor/título), landing, `/about`, `/api`, estadísticas.
- Monitorización: `/health`, `/metrics` (Prometheus), logging JSON.
- `verify-mirror` y `doctor` (incluido `--links`).
- CLI y API sobre los mismos casos de uso.

**V1.1 — CERRADA** (2026-08). Modelo Work / Resource / StorageLocation.

- Tabla `works` + `work_id` en `archive_entries` (Resource).
- `BuildWorks` (por hash PDMX) — 254,035 obras creadas.
- API `GET /api/v1/works` (búsqueda) y `GET /api/v1/works/{id}` (obra + representaciones).
- Páginas `/works` y `/works/{id}`.
- Responsabilidad clara: osap-storage sirve recursos individuales; **OSAP unifica** (también con
  otros repositorios).

**V2 — en planificación** (ver `docs/v2.md`): API Key, rate limiting, usuarios/auth (Google), panel de
administración, i18n (6 idiomas), metadatos completos.

**Fuera de V1:** Google Drive/S3 como proveedores, descarga bajo demanda de TAR, caché inteligente,
sincronización automática.

## Liberación a producción

- **`config.yaml`** — configuración de **desarrollo** (esta máquina).
- **`config.production.yaml`** — configuración de **producción** (gitignored). Al cerrar
  una versión se despliega en 91.134.255.134 como `config.yaml`.
- **`release.ps1`** — script PowerShell de liberación: tests+lint → sube el código
  (tar+ssh) → despliega `config.production.yaml` como `config.yaml` → migraciones →
  reinicia el servicio → verifica `/health`.

```powershell
.\release.ps1            # liberación completa
.\release.ps1 -SkipTests # sin tests/lint
.\release.ps1 -SkipMigrations
```

Producción solo se modifica al cerrar una versión; nunca durante el desarrollo.

## Criterios de mantenimiento

- La web y el CLI deben ser **clientes de la API/casos de uso**, nunca contener lógica de negocio.
- Toda la lógica reside en `domain/`, `application/` y la API.
- Mantener este documento y `structure.md` actualizados con cada cambio.
