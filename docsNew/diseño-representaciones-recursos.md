# Modelo `Work → Representation → Resource` — nota de diseño

Estado: **modelo cerrado, migración paralela ejecutada y app integrada (2026-09-18)**. Tablas
`representations`/`resources`/`representation_persons` creadas y pobladas en `osap-storage_test`
y `osap-storage`; la app ya las consume (§12). `archive_entries` intacto. Pendiente: decidir §11.
Fecha: 2026-09-18 · Ámbito: PDMX + CPDL + almacenamiento (`archive_entries`/`files`).

---

## 0. Decisiones cerradas

| # | Decisión |
|---|---|
| 1 | Jerarquía **Work → Representation → Resource** (explícita; elimina `works_type_file` de `works`). |
| 2 | **Representation** = forma concreta de la obra (edición, versión, arreglo, transcripción, fuente). **Resource** = fichero que la materializa. |
| 3 | `archive_entries` se **descompone** en `representations` + `works_resources` (no se reutiliza su nombre ni se mezclan niveles). |
| 4 | PDMX arranca con **1 representación por obra** porque los datos son 1:1 hoy; **no es regla del modelo**. |
| 5 | CPDL: cada **edición = 1 representación**; sus ficheros = recursos. `cpdl_editions`/`cpdl_edition_files` dejan de ser arquitectura definitiva. |
| 6 | Atributos: `cpdlno`→representación; licencia→representación; editor→representación/persona/rol; tipo de fichero→recurso; nombre/path/URL/estado→recurso. |
| 7 | **CPDLno NO es UNIQUE** (48 duplicados): se conserva como dato de procedencia; el `origin_id` será un identificador realmente único (§8.1). |
| 8 | Las **11.242 representaciones sin fichero se conservan** (licencia/editor reales). La validación del parser va aparte. |
| 9 | El recurso admite **`url` externa y `file_id`**: se puede inventariar sin obligar a descargar 217k ficheros. |
| 10 | **`storage_locations` sigue colgando de `files`**, no de `works_resources`. |
| 11 | **No se toca `archive_entries`** hasta demostrar con consultas que queda cubierto (§9). Transición aditiva. |

---

## 1. Motivo

1. **Los ficheros CPDL no aparecen en la aplicación.** `cpdl_edition_files` (217.343) sólo lo lee
   el importador y el CRUD genérico; no hay API, búsqueda ni descarga. **0 de las 56.420 obras
   CPDL tienen `archive_entries`**: el corpus se busca pero no ofrece ni un recurso.
2. **No existe el nivel "representación".** Cadena actual `works → archive_entries → files`, con
   `archive_entries` haciendo de representación y recurso a la vez (1:1: 254.035 entradas, 0 obras
   con más de una). Síntoma: `works.works_type_file` (atributo de un fichero) en `works`.

---

## 2. Modelo propuesto

```
works
  └── representations
          └── resources
                  └── files (identidad digital: sha256, mime, size)
                          └── storage_locations (copias físicas por proveedor)
```

`representations` (prefijo de tabla según convención):

| Columna | Notas |
|---|---|
| `id` | PK |
| `representations_works_id` | FK `works(id)` |
| `representations_origin` | `pdmx` \| `cpdl` \| … |
| `representations_origin_id` | id único en el origen (ver §8.1 para CPDL; PDMX: ver §4) |
| `representations_origin_cpdlno` | procedencia CPDL (no único), nullable |
| `representations_type` | `edition` \| `score` \| `arrangement` \| `transcription` \| `manuscript` \| … (§8.3) |
| `representations_source_name` | nombre/título crudo en el origen ← `archive_entries.logical_id` (§3.1) |
| `representations_license` | licencia (CPDL: por edición) |
| `representations_created_at/updated_at` | |

`works_resources` (renombrada desde `resources` el 2026-09-19, por coherencia con `works_person_roles`):

| Columna | Notas |
|---|---|
| `id` | PK |
| `works_resources_representation_id` | FK `representations(id)` |
| `works_resources_type` | `MXL` \| `PDF` \| `MIDI` \| `MP3` \| `CAPX` \| … (sustituye a `works_type_file`) |
| `works_resources_name` | nombre del fichero en el origen |
| `works_resources_relative_path` | ruta en el archivo/mirror (si aplica) |
| `works_resources_status` | estado del recurso (semántica a unificar) |
| `works_resources_file_id` | FK `files(id)` NULL — fichero digital |
| `works_resources_url` | URL externa de procedencia (NULL si es interno) |
| `works_resources_archive_id` | FK `archives(id)` NULL ← `archive_entries.archive_id` (§3.1) |
| `works_resources_created_at/updated_at` | |

`files` y `storage_locations` **no cambian** (decisión 10).

Personas de una representación (editor, rol 6): junction `representation_persons`
(equivalente a `cpdl_edition_persons`: persona + rol + nombre crudo).

---

## 3. Mapeo desde el esquema actual

### 3.1 `archive_entries` (254.035) → `representations` + `works_resources`

Relleno real: `work_id`, `file_id`, `logical_id`, `relative_path` al 100 %; `composer`, `title`,
`size`, `offset_bytes` **todos NULL**. Status: **254.030 `missing`**, 5 `ready` (la
disponibilidad real en código se deriva de `file_id IS NOT NULL`, no de `status`).

| Origen | Destino | Motivo |
|---|---|---|
| `archive_id` | `resources_archive_id` | procedencia **física** del fichero; PDMX sirve MXL/PDF/MID en TARs distintos (§4) |
| `logical_id` | `representations_source_name` | no es un id: son títulos (130.605 distintos/254.035; sólo 883 con `:`); nombra la canción, no el fichero (§4) |
| `composer`, `title` | **descartar** | vacíos |
| `work_id` | `representations_works_id` | |
| `relative_path` | `resources_relative_path` | |
| `file_id` | `resources_file_id` | |
| `size`, `offset_bytes` | **descartar** | vacíos |
| `status` | `resources_status` | corregir semántica (`missing` con `file_id` presente) |

### 3.2 `files` (254.035)

Sin cambios. `resources.resources_file_id` los referencia. `files.sha256` sigue NULL.

### 3.3 `storage_locations` (254.035, 1 proveedor, todas `stored`)

Sin cambios: cuelgan de `file_id` (decisión 10).

### 3.4 `works`

| Origen | Destino |
|---|---|
| `works_type_file` (`MXL` en 254.035; NULL en las 56.420 CPDL) | `resources.resources_type`; **se elimina de `works`** |
| `works_relative_path` (0 con valor) | columna muerta → descartar |
| `works_origin`, `works_origin_id` | se mantienen en `works` (procedencia de la obra) |

### 3.5 `cpdl_editions` (81.983) → `representations`

`origin='cpdl'`, `license` → `representations_license`, `cpdlno` →
`representations_origin_cpdlno` (procedencia, no único) y `origin_id` único (§8.1).

### 3.6 `cpdl_edition_files` (217.343) → `works_resources`

`name` → `resources_name`; `type` → `resources_type`; `file_id` NULL; `relative_path` NULL;
`status`/`url` según §7.

### 3.7 `cpdl_edition_persons` (80.166) → `representation_persons`

`persons_id` + rol 6 + nombre crudo.

### 3.8 `archives` (1 fila: `mxl.tar.gz`, Zenodo, `G:/osap-storage`)

Procedencia del recurso (`resources_archive_id`). PDMX publica además `pdf.tar.gz` (9,6 GB) y
`mid.tar.gz` (214 MB), **no importados aquí**: cuando se importen, sus recursos colgarán de sus
propios `archives`.

---

## 4. Caso PDMX

Fuente: **PDMX — Public Domain MusicXML Dataset** (Long et al., Zenodo 15571083; derivado de
partituras de MuseScore). Cada *song* del dataset tiene MusicRender, metadata JSON y, cuando
está disponible, **MXL + PDF + MID**. En esta BBDD sólo se importó `mxl.tar.gz`, de ahí 1 único
`archive_entry` por obra.

- 254.035 obras PDMX, **1 representación por obra hoy** (coincidencia de datos, decisión 4).
- **Representación** = la *song* PDMX (una partitura de MuseScore). `origin='pdmx'`,
  `origin_id = work_key` (hash PDMX, único), `type='score'`.
- **Recursos**: el MXL actual; PDF y MID serán recursos de la **misma** representación cuando se
  importen (argumento decisivo para que `archive_id` viva en el **recurso**, no en la
  representación).
- `representations_source_name` ← `logical_id`. Evidencia: valores título ('Wiegenlied',
  'The Blind Guide'); `works_title` se construyó como `logical_id` + `" - " + compositor`
  (133.250 coincidencias exactas de 254.035, el resto enriquecido desde metadata MuseScore).
- `works_type_file` desaparece; su valor (`MXL`) pasa al recurso.

## 5. Caso CPDL

- 56.179 obras con ediciones (de 56.420). Distribución: **42.776 obras con 1 edición**, 8.740 con
  2, … hasta **50** ediciones. Multiplicidad real y frecuente.
- Cada edición = 1 representación (`origin='cpdl'`, licencia, editor); sus ficheros = recursos
  (3,07 de media; máximo 225).
- Licencias por edición: CPDL 48.163 · Personal 15.688 · Public Domain 6.820 · CC (varias)
  ~9.293 · vacía 768 · Religious 453 · GnuGPL 139.
- Todos los `cpdl_editions.works_id` apuntan a obras `origin='CPDL'` (0 discrepancias).

## 6. Las 11.242 representaciones sin fichero — **se conservan** (decisión 8)

No son basura: **10.902 con licencia y 10.198 con editor**. Se conservan como representación sin
recursos (metadata-only). La validación del parser (una edición con **225 ficheros** frente a
media 3,07) es una tarea separada y no bloquea el modelo.

## 7. Procedencia y URL de los recursos — **`url` + `file_id`** (decisión 9)

Los 217.343 nombres son simples (`ws-broo-cr2.pdf`): **0 con `/`**, 1 con `http`. El modelo admite
las dos vías sin obligar a descargar:

- `resources_url` (inventario / externo) y `resources_file_id` (interno, si se materializa).
- `resources_status` distingue `external`/`stored`/`missing`/…; hay que **unificar** la semántica
  con `archive_entries.status` (hoy `missing` en 254.030 pese a tener `file_id`).
- Materializar 217k ficheros es una decisión posterior y depende de la licencia por
  representación (Personal/CC-ND no son redistribuibles igual).

---

## 8. Puntos resueltos (confirmados 2026-09-18)

### 8.1 `representations_origin_id` para CPDL

`cpdlno` no es único (48 duplicados entre páginas). **Decidido**: `origin_id = f"{page_id}:{cpdlno}"`,
donde `page_id` ya está en `works.works_origin_id`; es único y estable. El `cpdlno` se conserva
además en `representations_origin_cpdlno`.

### 8.2 `logical_id` → `representations_source_name`, `archive_id` → `resources_archive_id`

**Decidido**, con la evidencia de §3.1/§4: `logical_id` es el título/nombre del origen (no un id:
130.605 distintos/254.035) y `works_title` lo compone/enriquece, por lo que se conserva crudo en
la representación. `archive_id` es la procedencia **física** del fichero (PDMX sirve MXL/PDF/MID en
TARs distintos), por lo que vive en el recurso.

### 8.3 Tipo de la representación PDMX

El MXL es la exportación MusicXML de una *song* de MuseScore (dataset PDMX). **Decidido**: tipo
**`score`** (partitura digital), distinto de `edition` (CPDL).

---

## 9. Regla de seguridad de la migración (obligatoria)

> **No borrar ni migrar `archive_entries` hasta demostrar mediante consultas que su información
> queda completamente representada en `representations` + `works_resources`.**

Construcción **aditiva** (crear representaciones/recursos en paralelo, sin tocar `archive_entries`).
Antes de retirar nada, en `osap-storage_test`, deben pasar:

1. **Cobertura total**: `SELECT COUNT(*) FROM archive_entries ae WHERE NOT EXISTS (...)` → 0.
2. **Recuentos**: `COUNT(resources)` (parte PDMX) == `COUNT(archive_entries)`.
3. **Ninguna obra pierde su recurso**: toda obra con `archive_entry` tiene ≥1 representación con
   ≥1 recurso.
4. **`file_id` y `relative_path` preservados** exactamente.
5. **Procedencia**: `archive_id` y `logical_id` presentes en el destino.
6. Sólo entonces: renombrar `archive_entries` a `archive_entries_bak` (no borrar) y validar la app.

Hasta que 1–5 den limpio, `representations`/`works_resources` son **paralelas** y la app sigue igual.

### 9.1 Ejecutado (2026-09-18)

`scripts/migrate_representations_resources.sql` (DDL, 3 tablas vacías) +
`scripts/migrate_to_representations.py` (INSERT..SELECT aditivo e idempotente; borra y recrea
solo las representaciones). Aplicado a **`osap-storage_test` y `osap-storage`**:

| | |
|---|---|
| `representations` | **336.018** (254.035 `pdmx` + 81.983 `cpdl`) |
| `works_resources` | **471.378** (254.035 MXL PDMX + 217.343 CPDL) |
| `representation_persons` | **80.166** |
| `archive_entries` sin representación | **0** |
| obras con `archive_entry` sin recurso | **0** |

`archive_entries` y `cpdl_*` **intactos** (transición aditiva). La app todavía **no** lee las
tablas nuevas. `ruff` limpio y 265 tests en verde tras la migración.

---

## 10. Fuera de alcance (trabajo posterior)

- Re-parseo/validación de ficheros por edición CPDL (incl. las 11.242 sin fichero).
- `sha256` de `files`.
- §11 (voicing/`work_parts`, materialización CPDL, retirada de `cpdl_*`).

La integración de app/API (GetWork, provider DTO, descarga, CRUD) está hecha: ver §12.

## 11. Decisiones aún abiertas

1. **Semántica de Representation y colocación de `voicing`/`work_parts`**: **§11 cerrado**
   (D1, D2, D3=A, D4) en **`docsNew/diseño-semantica-representacion.md`**. Sin nuevo nivel
   persistente: Representation/Work se resuelven por **agrupación** de recursos; `representations`
   queda como inventario de origen. No más migraciones por esto.
2. Materialización de recursos CPDL (depende de licencia por representación).
3. Tablas `cpdl_*`: staging o retirada tras migrar.

---

## 12. Integración de la aplicación (2026-09-18)

La app ya consume el modelo nuevo, manteniendo `archive_entries`/`cpdl_*` como compatibilidad.

1. **GetWork / SearchWorksFull** (`application/use_cases/works.py`): usan
   `RepresentationRepository` (`list_by_work[_ids]` + `list_resources_by_representation_ids`).
   `WorkDetail` gana `representations: list[RepresentationDetail]`; `resources` (plano) se
   mantiene como vista agregada. Si no se inyecta el repo, cae a `archive_entries` (compatibilidad).
   SQL: `SqlRepresentationRepository`.
2. **Provider DTO** (`api/routes/provider.py`, `api/schemas.py`): **aditivo**.
   `ProviderWorkRead.representations: list[ProviderRepresentationDTO]`
   (`id`, `origin`, `type`, `license`, `source_name`, `resources`). El array `resources` plano se
   conserva (solo disponibles). Los recursos de inventario (CPDL) aparecen con `available=false` y
   `links.download=null`.
3. **Descarga** (`GET /api/download/{resource_id}`): resuelve por `resources.id`
   (`file_id` → CDN/contenido, o `url` externa → 302). Si el id no es un recurso, cae al
   `files.id` legacy (enlaces antiguos).
4. **CRUD genérico**: whitelist ampliada con `representations`, `works_resources`,
   `representation_persons`.

**Pruebas**: `tests/integration/test_api_contracts.py` (+2 PDMX/CPDL) y
`test_repository_contracts.py` (+1 del repositorio). Suite completa **268 en verde**, `ruff` limpio.

**Verificado en vivo** (`osap-storage`): obra PDMX 1 → 1 `pdmx/score` con recurso MusicXML y
`/api/download/{id}` → 302 al CDN; obra CPDL 262488 → **46** `cpdl/edition` con sus recursos
(inventario, sin descarga aún); `/api/admin/tables` expone las tres tablas nuevas.

**Compatibilidad**: `archive_entries` y `cpdl_*` siguen intactos y siguen sirviendo la descarga
legacy; no se retiran hasta cerrar §11.
