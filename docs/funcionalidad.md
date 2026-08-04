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
- **`File`** — un fichero que **ya pertenece a OSAP** (materializado).
- **`StorageLocation`** — dónde está almacenada una copia del `File`.
- **`ImportSource`** — procedencia de cada índice importado (PDMX v1/v2, OpenScore, IMSLP dump...).

Nunca se crean `File` "vacíos": un `File` solo existe tras materializar (SHA256 calculado).
La descarga bajo demanda de TAR durante una petición HTTP queda **descartada**.

## Ingestión (offline)

Flujo: Proveedor (PDMX) → Importar índice → `Archive` → `ArchiveEntry` → Materializar →
extraer TODOS los MusicXML → SHA256 → `File` → `StorageLocation` → publicar en backend.

### `osap-storage import pdmx <csv> [--version] [--notes] [--archive-name <tar>] [--archive-url <url>]`

Construye el índice **sin descargar nada**: registra `Archive`s (deduplicados por nombre)
y `ArchiveEntry`s (estado `missing`). Idempotente (`INSERT IGNORE`).
Registra además un `ImportSource` con la procedencia del CSV (`--version` / `--notes`).

Auto-detecta columnas del CSV (`relative_path`, `archive`, `url`, `key`) o se pueden
indicar con `--relative-path-col`, `--archive-name-col`, `--archive-url-col`, `--logical-id-col`.
En PDMX real el archive no viene en una columna: se fija con `--archive-name` (p. ej. `mxl.tar.gz`)
y `--archive-url`, y la ruta de cada MusicXML con `--relative-path-col mxl`.
Valores vacíos o `NA`/`nan` se ignoran.

### `osap-storage materialize <archive_id> [--provider N] [--local-path ...] [--download] [--no-keep-tar]`

Descomprime un TAR completo, y por cada entrada: extrae → calcula SHA256 → registra `File`
(dedupe por SHA256) → publica en el backend → crea `StorageLocation` → marca `ready`.

- `--download`: si el TAR no está en `mirror.cache`, lo descarga desde `archive.url` a la caché
  (proceso offline; reutiliza el TAR si ya está en caché).
- `--no-keep-tar`: elimina el TAR de la caché tras materializar (solo si se descargó en esta ejecución).
- `--local-path`: usa un TAR ya disponible en disco sin descargarlo.

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

Fichero único `config.yaml` (o `OSAP_CONFIG`). Las variables de entorno y `.env`
tienen prioridad. Referencia:

```yaml
db:
  host/path/...            # Conexión a MariaDB/MySQL

http:
  host, port, public_base_url

storage:
  backend: local           # local | google_drive | s3
  local: { root: data/files }
  google_drive: { credentials: secrets/google.json, folder_id: xxxxx }

mirror:
  cache: data/cache        # TARs descargados durante la ingesta offline

providers:
  pdmx:
    source:
      csv: data/pdmx/pdmx.csv
      zenodo: { base_url: https://zenodo.org/records/XXXX }
```

El backend activo se elige con `storage.backend`; el proveedor por defecto se crea al arrancar
si no existe ninguno (`bootstrap.py`). En V1 el backend **implementado** es `local` (Filesystem);
`google_drive` y `s3` quedan definidos por interfaz pero pendientes.

## Estado por fases

**Implementado (V1):**
- Modelo de datos (archives/entries + files/locations + import_sources + statistics).
- Importador de índice PDMX offline (registra `ImportSource`).
- Materializador offline de TARs completos y materializador por fichero (`materialize-file`).
- Resolver de disponibilidad ("lo tengo / no lo tengo") + URL.
- Backend Filesystem + registro de backends por configuración.
- Operaciones locales: registrar existente, verificar, borrar.
- Estadísticas del repositorio (CLI `stats` + endpoint).
- CLI y API sobre los mismos casos de uso.

**Futuro (fuera de V1):**
- Google Drive y S3 como backends de publicación.
- Interfaz web de OSAP (cliente de la API: templates/routers/static).
- No está previsto: descarga bajo demanda de TAR en el tiempo de respuesta, caché inteligente, sincronización automática.

## Criterios de mantenimiento

- La web y el CLI deben ser **clientes de la API/casos de uso**, nunca contener lógica de negocio.
- Toda la lógica reside en `domain/`, `application/` y la API.
- Mantener este documento y `structure.md` actualizados con cada cambio.
