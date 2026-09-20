# Tabla de conversión — `osap-storage` → `osap-storage_new`

> Documento de trabajo. Fuente de datos: **dev** (`127.0.0.1`, BBDD `osap-storage` y `osap-storage_new`), consultado en solo-lectura. Los números son de dev; **hay que reconfirmarlos en producción antes de migrar** (ver §6).
> La migración se hará por **fork de la aplicación**. `osap-storage_new` **sustituye** a la antigua (no se cuenta con la vieja), y se subirá junto a los programas.

---

## 0. Decisiones cerradas

| # | Decisión |
|---|---|
| 1 | Los junctions vacíos (`work_genres`, `work_instruments`, `work_tags`, `work_parts`, `work_statistics`) **se crean y se construyen** (no se copian). |
| 2 | `musicbrainz_id` y `cluster_id` salen de `composers` y van a **identifiers**. La resolución de nombres de `composer` **no se hace ahora**: se hará después con el fichero descargado (`compositores_wikidata.json`, `scripts/load_composer_authority.py`). |
| 3 | **Voicing**: **JSON inline en `works.works_voicing`** (LONGTEXT utf8mb4_bin). Se descartaron las tablas `voicings` y `works_voicings`. |
| 4 | `work_language` = junction `work_id` + `language_id`. `work_tag` = junction `work_id` + `tag_id`. Catálogo de tags: `id`, `tag_texto VARCHAR(100)`, `tag_descripcion TEXT`. |
| 5 | Añadir `created_at`/`updated_at` donde se considere oportuno (ver §2). |
| 6 | Añadir **`works_key`** a `works`. **Copiar los almacenamientos** a la nueva BBDD. **Se descarta usar `works_obra_iden`.** |
| 7 | CPDL: se añaden todos los registros a `works` con `origin='CPDL'` y **`origin_id` = id de página MediaWiki (`<page><id>` del XML original)**, único y estable; hay que capturarlo al reimportar (el importador actual no lo lee). También existe `{{CPDLno|N}}` por edición (3633/5000 páginas, no siempre). |
| 8 | **Artist** no preocupa: antes de añadir hay que normalizar; se creará una **tabla de staging** `work_id, nombre, rol (compositor/artist)` y después se estudia. |
| 9 | Autoridad: **se migra todo** (las 30.148 de `composer_authority`). |
| 10 | Identificadores de persona → **`persons_identifiers`** (EAV). |
| 11 | Cuando termine, `osap-storage_new` **será** `osap-storage`. No se mantiene la BBDD antigua. |
| 12 | Runner de migraciones: el que convenga, después del arranque inicial. |
| 13 | **Fuente de datos = producción** (`osap_storage`, 91.134.255.134). **Dev se puede sobrescribir** ("grabar encima"). Las tablas `composer_*` del origen son `persons_*` en `_new`. |

---

## 1. Estado actual de `osap-storage_new`

| Origen | Destino | Filas | Estado |
|---|---|---|---|
| `works` | `works` | 254.035 → 254.035 (ids 1:1) | Parcial |
| `composers` | `persons` | 663 → 663 (UUID preservado) | Hecho |
| `composer_aliases` | `persons_aliases` | 2.420 → 2.420 | Hecho (idioma pendiente) |
| `epochs` | `epochs` | 7 → 7 | Hecho |
| `genres` / `genre_mappings` | igual | 12 / 16 | Hecho |
| `instruments` / `instrument_categories` | igual | 70 / 14 | Hecho |
| `votes` | `votes` | 0 → 0 | Hecho (vacío) |
| `catalogues` | `catalog` | 0 → 13 | Sustituido (seed) |
| — | `category`, `roles`, `roles_categoria` | 4 / 15 / 17 | Nuevo (seed) |

Roles relevantes ya sembrados: **1 = Compositor/a**, **10 = Intérprete / Solista**, 6 = Editor/a Musical.

---

## 2. Esquema creado en `osap-storage_new` — **aplicado** (2026-09-14, dev)

> DDL aditivo e idempotente ya ejecutado en dev `osap-storage_new`: 26 tablas nuevas + columnas en `works` y `persons`. Sin `DROP` ni cambios destructivos. `osap-storage_new` pasa de 15 a 41 tablas.
> Nombres según la normativa V3 (columnas con prefijo de tabla; FK mantiene el prefijo de la tabla referenciada). Si se prefiere la forma abreviada (`work_id`, `language_id`) se renombra después.

### 2.1 `works` — columnas nuevas
| Columna | Tipo | Nota |
|---|---|---|
| `works_key` | `VARCHAR(64) NULL UNIQUE` | hash de agrupación heredado |
| `works_created_at` | `DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)` | |
| `works_updated_at` | `DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)` | |

### 2.2 Idiomas y junctions de `works`
- **`languages`**: `id`, `languages_code VARCHAR(16) UNIQUE`, `languages_name VARCHAR(120)`, timestamps.
- **`work_language`**: `works_id` FK→`works.id`, `languages_id` FK→`languages.id`, PK(`works_id`,`languages_id`), `work_language_created_at`.
- **`work_tag`** (junction): `works_id`, `tag_id` → catálogo, PK compuesta.
- **`tag_work`** (catálogo): `id`, `tag_texto VARCHAR(100) NOT NULL UNIQUE`, `tag_descripcion TEXT`, timestamps.
- **`work_genres`**: `works_id`, `genres_id`, PK compuesta. (a construir desde `works.genre`/`genre_id`)
- **`work_instruments`**: `works_id`, `instruments_id`, PK compuesta.
- **`work_parts`**: `id`, `works_id`, `work_parts_name VARCHAR(512)`, `created_at`.
- **`work_statistics`** (prefijo `wksta_`): `works_id` PK, `wksta_vote_count`, `wksta_work_count`, `wksta_confidence`, `wksta_rating`, `wksta_adjusted_rating`, `wksta_calculated_at`.

### 2.3 Voicing (decisión 3) — **JSON inline, aplicado**
- `works.works_voicing` `LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin` con el JSON crudo de CPDL.
- `voicings` y `works_voicings` **se crearon y se eliminaron** (no se normaliza).

### 2.4 Personas — columnas y tablas
- **`persons`** (añadir):
  `persons_biography_summary TEXT`, `persons_biography_era VARCHAR(64)`, `persons_biography_nationality VARCHAR(64)`, `persons_biography_key_works LONGTEXT`, `persons_biography_key_fact VARCHAR(255)`, `persons_biography_references LONGTEXT`, `persons_biography_updated_at VARCHAR(64)`.
- **`persons_identifiers`** (decisión 2/10): `id`, `persons_id` FK, `persons_identifiers_type VARCHAR(24)`, `persons_identifiers_value VARCHAR(255)`, `persons_identifiers_source VARCHAR(32)`, `persons_identifiers_is_identity_anchor TINYINT(1)`, `persons_identifiers_strength VARCHAR(16)`, `persons_identifiers_channels LONGTEXT`, `created_at`.
  Origen: `composer_identifiers` (5.102 / 663 personas, 12 tipos) **+** `musicbrainz_id` (tipo `musicbrainz`) **+** `cluster_id` (tipo `cluster`).
- **`persons_authority`** (decisión 9): `authority_id` PK, `persons_id CHAR(36) NULL` (enlace a resolver), `persons_authority_wikidata_id`, `..._viaf_id`, `..._imslp_id`, `..._canonical_name`, `..._birth_date`, `..._death_date`.
  Origen: `composer_authority` (30.148).
- **`persons_authority_name`**: `id`, `authority_id` FK, `persons_authority_name_name`, `..._normalized_name`, `..._source`. Origen: `composer_authority_names` (30.148).
- **`persons_evidence`**: espejo de `composer_evidence` (663).
- **`persons_merge_history`**: espejo de `composer_merge_history` (4).

### 2.5 Staging de atribución (decisión 8)
- **`works_person_import`**: `id`, `works_id`, `works_person_import_name VARCHAR(1024)`, `works_person_import_role VARCHAR(16)` (`composer`/`artist`), `works_person_import_source VARCHAR(32)`, `works_person_import_resolved TINYINT(1) DEFAULT 0`, `created_at`.
  Se usarán **todos los nombres** (`works.composer` 90.968 / 37.246 distintos; `works.artist` 238.632 / 14.981 distintos) sin resolver todavía.

### 2.6 Almacenamiento (decisión 6)
Copiar tal cual desde la antigua: `archives`, `archive_entries`, `files`, `storage_locations`, `storage_providers`, `import_sources`, `download_jobs`, `statistics`, `statistics_runs`.
(No `musicbrainz_cache`.)

### 2.7 Infra
- **`schema_migrations`**: `id`, `name UNIQUE`, `applied_at`.

---

## 3. Tabla maestra de conversión

### 3.1 `works` (254.035 filas, id 1:1)

| Origen | Filas con dato | Destino | Regla |
|---|---|---|---|
| `id` | 254.035 | `works.id` | directo |
| `title` | 254.035 | `works.works_title` | directo |
| `song_name` | 3 | `works.works_song_name` | directo |
| `subtitle` | 39.371 | `works.works_subtitle` | directo (hoy guarda `NA`) |
| `attribution_type` / `attribution_note` | 0 / 0 | `works_attr_type` / `works_attribution_note` | directo |
| `opus` / `year` | 0 / 0 | `works_opus` / `works_year` | directo |
| `catalogue` | 5 | `works_catalogue` | directo; futuro desde `catalog` (regex) |
| `musical_key` | 5 | `works_musical_key` | directo |
| `duration`/`measures`/`pages`/`parts`/`complexity`/`description` | 0 | `works_*` | directo |
| `license` | 254.035 | `works_license` | directo |
| `public_domain` | 5 | `works_public_domain` | directo |
| `relative_path` | 0 | `works_relative_path` | directo |
| `music_digest` | 254.032 | `works_music_digest` | directo |
| **`work_key`** | **254.035** | **`works.works_key`** (nueva) | directo |
| `composer` (texto) | 90.968 (37.246 distintos) | `works_person_import` (rol `composer`) → `works_person_roles` (role 1) | todos pasan a `persons` |
| `composer_id` | 3.323 | `works_person_roles` (role 1) | FK directa (`persons.persons_id`; los 3.323 existen) |
| `artist` | 238.632 (14.981 distintos) | `works_person_import` (rol `artist`) → `works_person_roles` (role 10) | normalizar antes |
| `genre` (texto) | 82.786 | `work_genres` | vía `genre_mappings.code` |
| `genre_id` | 80.839 | `work_genres` | FK directa a `genres.id` (preferente) |
| `language` | 0 | `work_language` | sin datos en works (usar CPDL) |
| `tags` | 0 | `work_tag` | sin datos |
| `instrumentation` | 0 | `work_instruments` | sin datos |
| `thumbnails` | 0 | — | descartar |
| `created_at`/`updated_at` | 254.035 | `works_created_at`/`works_updated_at` | mapear timestamp |

Nuevas en `works`: `works_epoch_id`, `works_origin`, `works_origin_id`, `works_type_file` (hoy 100 `OMR`), `works_obra_iden` (en desuso por decisión 6).

### 3.2 Personas (composers → persons)

| Origen | Filas | Destino | Nota |
|---|---|---|---|
| `composers` | 663 | `persons` | Hecho; UUID preservado |
| `composer_aliases` | 2.420 | `persons_aliases` | Hecho; `language` → `language_id=0` (idioma perdido → reconstruir con `languages`) |
| `musicbrainz_id` | 640 | `persons_identifiers.type='musicbrainz'` | decisión 2 |
| `cluster_id` | 640 | `persons_identifiers.type='cluster'` | decisión 2 |
| `homepage` | 0 | — | sin datos |
| `suspicious` / `suspicious_reason` | 0 | — | sin datos |
| `composer_biographies` | 310 | `persons.persons_biography_*` | requiere columnas nuevas |
| `composer_authority` | 30.148 | `persons_authority` | se migra todo (decisión 9); enlace a `persons` pendiente |
| `composer_authority_names` | 30.148 | `persons_authority_name` | |
| `composer_identifiers` | 5.102 (663 personas) | `persons_identifiers` | + musicbrainz_id/cluster_id |
| `composer_evidence` | 663 | `persons_evidence` | |
| `composer_merge_history` | 4 | `persons_merge_history` | |
| `authority_sync_state` | 0 | copiar | vacío |
| `authority_identifiers` | 0 | descartar | vacío |
| `composer_statistics` | no existe | — | — |

Identificadores presentes en `composer_identifiers`: viaf (1.023), isni (679), discogs (664), musicbrainz (644), gnd (385), ipi (371), bnf (307), lccn (291), imslp (272), wikidata_qid (250), rism (195), mbid (21).

### 3.3 CPDL (`cpdl_pages` → `works`)

`cpdl_pages` = 76.144. Relleno: `title` 76.144, `composer` 63.569, `catalogue_hint` 1.514, `voicing` 55.239, `instrumentation` 55.278, `genre` 55.484, `language` 55.433, `payload_json` 76.144, `n_editions>0` 55.306.

| Origen | Destino | Nota |
|---|---|---|
| `cpdl_pages` (fila) | `works` | `works_origin='CPDL'`, `works_origin_id` = id página MediaWiki, **se añaden todos** |
| `title` | `works_title` | |
| `composer` | `works_person_import` (composer) | + `payload` para work↔person |
| `catalogue_hint` | `works_catalogue` | |
| `license` | `works_license` | |
| `voicing` (JSON array) | `voicings` + `works_voicings` | 1.376 términos distintos |
| `genre` (JSON array) | `work_genres` (vía `genre_mappings`) | |
| `language` (JSON array) | `languages` + `work_language` | |
| `instrumentation` (JSON array) | `work_instruments` | |
| `payload_json` | `works_person_import` / `works_person_roles` | editores de las ediciones → persona (role 6?) |
| `n_editions` / `arrangement_hint` | — | sin destino definido |

**Contenido de `payload_json`:** `{"editions":[{"cpdlno","files":[...],"editor","license"}]}`, hasta 50 ediciones.
Ejemplo: `{"editions":[{"cpdlno":"55510","files":["...mxl","...pdf"],"editor":"Matthew Collins","license":"CPDL"}]}`.

### 3.4 Almacenamiento (a copiar tal cual)

| Tabla | Filas | Uso |
|---|---|---|
| `archives` | 1 | índice de tar |
| `archive_entries` | 254.035 | recurso ↔ obra (`work_id`, `relative_path`) |
| `files` | 254.035 | fichero físico (`sha256`, `size`) |
| `storage_locations` | 254.035 | ubicación (`object_key`, `provider_id`) |
| `storage_providers` | 1 | proveedor (local/R2) |
| `import_sources` | 1 | trazabilidad |
| `statistics` / `statistics_runs` | 4 / 63 | estadísticas y jobs |
| `download_jobs` | 0 | |
| `musicbrainz_cache` | 0 | descartar |

### 3.5 Junctions vacías en origen (crear y construir)

`work_genres`, `work_instruments`, `work_tags`, `work_parts`, `work_statistics`, `works_instruments` → **0 filas**. Se construyen desde `works.genre`/`genre_id` y del resto de fuentes.

### 3.6 No migrar

`composer_candidate`, `composer_identity_resolution`, `composer_resolution` (0 en dev; confirmar producción), `authority_identifiers` (0), `musicbrainz_cache` (0), `works.thumbnails` (0), `works.instrumentation`/`language`/`tags` (0 filas → no aportan), `works_obra_iden` (decisión 6).

---

## 4. Explicaciones

### 4.1 ¿Para qué se usa `work_key`?
Hash derivado (`work_key_of()` = basename de `relative_path` sin extensión; p. ej. CID PDMX `QmbbGK...`). Es la **clave de agrupación/dedup**: UNIQUE, la usan `SqlWorkRepository.get_by_work_key`, `BuildWorks` (agrupa `archive_entries` y crea una Work por hash), `external_works`, `composer_recovery` y los scripts `backfill_works_pdmx.py` / `analyze_works_content.py`. En el modelo nuevo se conserva como columna `works_key`.

### 4.2 ¿Los almacenamientos se usan o solo fueron la carga inicial?
**Se usan.** `GET /api/download/{resource_id}` resuelve por `archive_entries.get_by_file_id` → `relative_path` → URL de CDN. Además los usan `start_download`, `stream_file`, `get_download_url`, `verify_file`, `delete_file`, `mirror_resources`, `file_publisher`, `/health`, `/statistics` y `analyze_works_content.py`. Por eso se copian.

### 4.3 Género: `genre` (texto) vs `genre_id`
`genre_id` presente en 80.839; `genre` en 82.786 (171.249 son `NA`). `genre_mappings` traduce código→id, pero hay **148 códigos sin mapear** (`hiphop`, `rock-folk`, `classical-experimental`, `metal`, ...; ~5.000 filas). Se usa `genre_id` como primario y `genre_mappings` como respaldo.

### 4.4 Atribución: `composer` / `composer_id` / `artist`
- `composer_id`: 3.323, todos existen en `persons` → role 1 directo.
- `composer` texto: 90.968 / 37.246 distintos, solo 3.089 casan por nombre → **todos pasan a `persons`** (decisión 2).
- `artist`: 238.632 / 14.981 distintos, 4.809 casan → van a staging y se normalizan después.

---

## 5. Pendiente / a confirmar

1. **Nombres**: la decisión 4 usa `work_id`/`language_id`/`tag_id`; la normativa V3 usa `works_id`/`languages_id`. Confirmar cuál prevalece.
2. **Catálogo de tags**: nombres definitivos (`tag_work` vs `tags_work`; `tag_id` vs `tag_work_id`).
3. **`persons_authority` → `persons`**: enlace por `canonical_name`/`normalized_name` (no hay `person_id` en origen). ¿Solo las que casan o todas con `persons_id` NULL?
4. **`cluster_id`**: confirmar que es un identificador (¿qué esquema?) antes de volcarlo a `persons_identifiers.type`.
5. **Editores CPDL** (`payload.editions[].editor`): ¿se crean como personas con role 6 (Editor/a Musical), role 10 u otro?
6. **`works.created_at/updated_at`**: mapear los timestamps originales o dejar `NOW()`.
7. **`works_languaje`** (origen) vs `work_language` (decisión 4): confirmar nombre de tabla.
8. **Runner de migraciones**: set inicial y formato (¿el runner actual de osap-storage o uno nuevo?).
9. ~~**Datos de enriquecimiento**:~~ **Resuelto**: producción tampoco está enriquecida en BBDD (ver §6). La afirmación de `docs/v2.md` no se refleja en las columnas.

---

## 6. Producción vs dev (comprobado 2026-09-14, solo lectura vía SSH)

> **Actualización (2026-09-14):** dev `osap-storage` ya se ha **sobrescrito con una imagen exacta de producción** (ver §8). Las cifras de la columna "Dev antiguo" son del dev previo a la imagen.

`docs/v2.md` afirmaba que producción se enriqueció 254.035/254.035 obras (tonalidad, duración, compases, páginas, partes, instrumentos, tags). **No es así en la BBDD de producción `osap_storage` (91.134.255.134):**

| Columna en `works` | Prod | Dev |
|---|---|---|
| `musical_key` | 5 | 5 |
| `duration` | 0 | 0 |
| `measures` / `pages` / `parts` / `complexity` | 0 | 0 |
| `instrumentation` | 0 | 0 |
| `tags` | 0 | 0 |
| `description` | 0 | 0 |
| `thumbnails` | 0 | 0 |
| `license` | 254.035 | 254.035 |
| `public_domain` | 5 | 5 |

- Los JSON de enriquecimiento **sí están en disco** en prod: `/home/ocw/openmusicrepository.com/mirror/metadata/` (254.077 ficheros).
- Lo único materializado es `work_genres` en prod (**254.035 filas**, creadas 2026-09-07 18:31; 163 géneros distintos). En dev `work_genres` = 0.
- `works_instruments`, `work_instruments`, `work_tags`, `work_parts`, `work_statistics` = **0** en ambos.
- **Todas** las filas de prod tienen `updated_at >= 2026-08-17` y el máximo es `2026-09-07 18:31:12`, justo cuando se creó `work_genres`. Indica un **rebuild masivo de `works`** el 2026-09-07 que probablemente **borró el enriquecimiento** anterior.

**Más diferencias prod vs dev (importantes para elegir la fuente):**

| Tabla | Prod (= dev actual) | Dev antiguo |
|---|---|---|
| `composers` | **2.278** | 663 |
| `composer_aliases` | 4.269 | 2.420 |
| `composer_biographies` | 1.165 | 310 |
| `composer_identifiers` | 7.574 | 5.102 |
| `composer_authority` / `_names` | 30.148 / 30.148 | 30.148 / 30.148 |
| `composer_candidate` | 15.909 | 0 |
| `composer_identity_resolution` | 81.226 | 0 |
| `cpdl_pages` / `cpdl_voicings` | **0 / 0** | 76.144 / 60.718 |
| `works.music_digest` | 0 | 254.032 |
| `works.genre_id` (columna) | **no existe** | existe (80.839) |
| `work_genres` | 254.035 | 0 |
| `works_composer_bak_20260823` / `composer_candidate_bak_20260823` | 22.575 / 15.841 | no existen |

Conclusión: **prod es la fuente** (confirmado, decisión 13); dev se puede sobrescribir. Prod es más rica en personas/autoridad/identidad; el CPDL solo existe en dev (se cargará aparte). El enriquecimiento se recupera desde los JSON del mirror (ver §7).

---

## 7. Contenido de los JSON de enriquecimiento y decisión sobre voicing

### 7.1 Qué contienen los JSON (`mirror/metadata/<shard>/<id>.json`)

Son la respuesta de la API de MuseScore para cada score. El pipeline (`infrastructure/enrichment/metadata.py`) extrae exactamente:

| Campo del JSON | Se guarda en `works` |
|---|---|
| `data.score.keysig` | `musical_key` |
| `data.score.duration` | `duration` |
| `data.score.measures` | `measures` |
| `data.score.pages_count` | `pages` |
| `data.score.parts` | `parts` |
| `data.score.parts_names[]` | `instrumentation` (fallback) |
| `data.score.instruments[].name` | `instrumentation` |
| `data.score.tags[]` | `tags` |
| `data.score.thumbnails` | `thumbnails` (JSON) |
| `data.score.description` / `truncated_description` | `description` |
| `data.score.license` / `is_public_domain` | `license` / `public_domain` |
| `data.genres[].name` | `genre` |
| `data.score.composer_name`, `title`, `subtitle` | `composer`/`title`/`subtitle` |
| CSV PDMX (`composer_name`, `artist_name`, `song_name`, `genres`, `tags`, `license`, `complexity`) | `composer`, `artist`, `song_name`, `genre`, `tags`, `license`, `complexity` |

Es decir, los 254.077 JSON del mirror contienen justo el enriquecimiento que hoy está a NULL en `works` (tonalidad, duración, compases, páginas, partes, instrumentos, tags, thumbnails, description). **Reejecutar el enriquecimiento los persiste.**

### 7.2 Voicing: resuelto — **JSON inline** (2026-09-14)

- Decisión: **no se normaliza**. El voicing de CPDL se guarda tal cual en `works.works_voicing` (LONGTEXT utf8mb4_bin).
- Se eliminaron las tablas `voicings` y `works_voicings` que se habían creado.
- Consecuencia: no hay búsqueda por término de voicing a nivel de BBDD (se puede hacer con `JSON_SEARCH`/`LIKE` sobre `works_voicing` si hiciera falta).

---

## 8. Dev `osap-storage` = imagen de producción (2026-09-14)

- **Hecho**: dump completo de producción (`osap_storage`, MariaDB 11.8.3, 42 tablas, ~388 MB) → restaurado en dev `osap-storage` (MariaDB 10.4.32). Se recreó la BBDD y se importó (353 s).
- **Verificado**: 42 tablas y conteos idénticos (works 254.035, work_genres 254.035, archive_entries 254.035, files 254.035, storage_locations 254.035, composers 2.278, composer_candidate 15.909, composer_identity_resolution 81.226, cpdl_pages 0, work_instruments 0). `works.genre_id` ya no existe (coincide con prod).
- **Portabilidad**: el dump traía la línea `/*M!999999\- enable the sandbox mode */` (MariaDB 11) que el cliente 10.4 no entiende; se eliminó. Todo lo demás era compatible (`utf8mb4_unicode_ci`).
- **Backup del dev anterior**: `C:\Users\migarcia\AppData\Local\Temp\kilo\dev_osap-storage_backup_20260914.sql` (258,9 MB) — conserva el CPDL (76.144) y los `music_digest` (254.032) del dev previo.
- **CPDL reimportable**: los originales están en `G:\ChoralWiki-20260903154414.xml` y `G:\cpdl_chunks\cpdl-*.xml`. Se puede repetir la importación con `scripts/import_cpdl_pages.py`, esta vez apuntando a `works` (`origin='CPDL'`).
- **Autoridad de nombres**: fuente original en `D:\Proyectos\AI_OSAP\osap-compositores\Carga\compositores_wikidata.json` (`scripts/load_composer_authority.py`).
- `osap-storage_new` (destino de la migración) **no se ha tocado** en esta operación.

---

## 9. Conversión ejecutada — fase 1 (núcleo), 2026-09-14

Script: `scripts/migrate_to_new.sql` (re-ejecutable: vacía el destino y recopia). Origen `osap-storage` (imagen prod) → `osap-storage_new`.

| Destino | Filas | Origen |
|---|---|---|
| `persons` | 2.278 | `composers` |
| `persons_aliases` | 4.269 | `composer_aliases` (+ 60 idiomas) |
| `persons_identifiers` | 8.896 | `composer_identifiers` + `musicbrainz_id`/`cluster_id` |
| `persons_authority` | 30.148 (2.310 enlazadas a `persons`) | `composer_authority` |
| `persons_authority_name` | 30.148 | `composer_authority_names` |
| `persons_evidence` | 2.278 | `composer_evidence` |
| `persons_merge_history` | 4 | `composer_merge_history` |
| `works` | 254.035 | `works` (columnas directas + `works_key`) |
| `works_person_roles` | 23.897 | `works.composer_id` (rol 1) |
| `works_person_import` | 319.116 | textos `composer` (80.484) + `artist` (238.632) |
| `work_genres` | 80.839 | `works.genre` vía `genre_mappings` |
| `files` / `storage_locations` / `archive_entries` | 254.035 cada | copia literal |
| `statistics_runs` | 71 | copia literal |

Pendiente de la conversión:

1. ~~**Enriquecimiento**~~ **Hecho (2026-09-15)** sobre la imagen de prod (`osap-storage`): `enrich-metadata` con el mirror completo (`metadata/` 254.077 JSON + `PDMX.csv`, descargados de prod). Resultado: 254.019/254.035 obras con `musical_key`/`duration`/`measures`/`pages`/`parts`/`instrumentation`/`thumbnails` (254.035), `description` 237.888, `tags` 20.730. Junctions del esquema viejo pobladas: `work_parts` 408.971, `work_instruments` 350.946, `work_tags` 20.853, `work_genres` 82.786. 16 errores por duplicados en `work_parts`; avisos de truncado en `work_tags.tag` (varchar 512). Falta **propagar** esto a `_new` (re-ejecutar la conversión + reimportar CPDL).
2. ~~**CPDL**~~ **Hecho (2026-09-14)**: `scripts/import_cpdl_works.py` (nuevo) importa `G:\cpdl_chunks\*.xml` → `works` con `works_origin='CPDL'`, `works_origin_id` = id de página MediaWiki y `works_voicing` (JSON inline). 56.420 works (21.163 páginas descartadas por no parecer obra). Idiomas → `languages` (132) + `work_language` (56.426). Compositores → `works_person_import`.
3. ~~Resolución de nombres~~ **Hecho (2026-09-15)**: `scripts/resolve_persons.py` resuelve los compositores de `works_person_import` a `persons` (por nombre, alias o autoridad `persons_authority_name`) y crea `works_person_roles` (rol 1). Resultado: **36.197 personas** (+33.919) y **139.631 relaciones**; 3.039 autoridades enlazadas. Los **artistas siguen en staging** (sin resolver, por decisión).
4. ~~`genre_mappings`~~ **Hecho**: 165 mapeos (códigos base nuevos + compuestos por segmento inicial); **0 códigos sin mapear**. `work_genres` = 82.786.
5. ~~Junctions~~ **Hecho**: `work_parts` **408.971**, `work_tags` **20.853** (`tag_work` 16.756), `work_language` **56.426** (solo CPDL; `works.language` de PDMX está vacío), `work_instruments` **333.872**.
6. ~~Voicing~~ **Hecho** vía `voices`/`work_voices` + `ensembles`/`work_ensembles` (ver §10).

**Residual conocido**: 2.421 textos de instrumentación de CPDL sin normalizar (estilos/frases libres); artistas sin resolver.

---

## 10. Modelo de instrumentación/voces/ensembles (2026-09-15)

Diseño acordado: **catálogos** (`instruments`, `voices`, `ensembles`) + **relaciones con la obra** (`work_instruments`, `work_voices`, `work_ensembles`) + **composición** (`ensemble_voices`). Familias = `instrument_categories` (jerarquía ya existente); los registros de `instruments` son las variantes.

Esquema creado (`scripts/migrate_instrumentation_schema.sql`):
- `voices(id, voices_name UNIQUE, voices_sort)` — 9: Soprano, Mezzo-soprano, Contralto, Countertenor, Tenor, Baritone, Bass, Treble, Voice.
- `ensembles(id, ensembles_name, ensembles_code UNIQUE, ensembles_description)`
- `ensemble_voices(ensembles_id, voices_id, ensemble_voices_quantity, ensemble_voices_order)`
- `work_voices(works_id, voices_id, work_voices_quantity, work_voices_context)` — contexto `solo`/`ensemble`.
- `work_ensembles(works_id, ensembles_id, work_ensembles_quantity)`
- `work_instruments` + `work_instruments_quantity`.
- Se **movieron fuera de `instruments`** los 8 registros de voz (cat 107) y 4 de ensemble (cat 108): 70 → 58 instrumentos reales.

Poblado (`scripts/map_instrumentation.py`, clasificador único):
- Fuente: `osap-storage`.`work_instruments` (textos enriquecidos, cantidad del sufijo `(N)`) + `works.works_voicing` + `works.works_instrumentation` (CPDL, columna nueva).
- **`work_instruments` 333.872** (47.450 con cantidad > 1), **`work_voices` 30.767** (contexto solo/ensemble), **`work_ensembles` 96.453**.
- Catálogo ampliado a **144 instrumentos** (`scripts/migrate_instruments_expand.sql` y `_expand2.sql`): variantes que faltaban (Woodblock, Claves, Harmonica, Tom tom, Conga, Bongo, Sitar, Erhu, Nyckelharpa...) y grupos/secciones (Drum group, Strings group, Orchestra, String/Wind/Brass ensemble...). `ensembles` = 388 (los códigos de CPDL se crean al vuelo), `voices` = 9.
- **Origen (PDMX): 0 textos sin mapear.** Residual **CPDL: 2.421 textos distintos** (mayoría estilos/frases libres y plantillas: `A cappella or keyboard`, `Choral soprano solo`, `: 2 violins`, `add=...`, `{{Cat...`), no normalizables automáticamente.
- Instrumentación de CPDL ya integrada (`works.works_instrumentation` → modelo).

---

## 11. PENDIENTE TÉCNICO — normalización de nombres/títulos dispersa (2026-09-17)

> **No es un paso de migración de datos**, pero afecta a la migración porque las claves de identidad (`persons_identity.identity_name_norm`, `persons_aliases.person_aliases_normalized_alias`, `composer_key`, `work_key`) dependen de ella. Se deja anotado para retomarlo **después** de la migración (o cuando se toque identidad otra vez).

**Situación**: cada aplicación tiene una función normalizadora canónica, pero está rodeada de copias locales y las dos apps **no normalizan igual**.

| | Función canónica | Copias locales |
|---|---|---|
| `osap-storage` | `domain/services/composer_names.py:9` `normalize_composer_name` (usada por ~13 módulos) | ~15 scripts con versión propia |
| `osap-api` | `src/osap/domain/normalization.py:6` `normalize_name` | 5 scripts con `composer_key` + ~8 módulos `src/` con `_norm`/`_strip`/variantes |

**Evidencia (file:line):**

1. **`composer_key` (iniciales + apellido) duplicado ~12 veces**: `osap-storage` en `candidate_cleanup.py:78`, `incorporate_candidates.py:44`, `incorporate_resolutions.py:44`, `test_authority_coverage.py:39`, `resolve_persons.py:53`, `link_works_person_import.py:67`, `load_composer_authority.py:35`; `osap-api` en `index_works.py:74`, `identity_resolver.py:57`, `build_composer_index.py:30`, `enrich_identifiers.py:30`, `diagnose_not_found.py:31`. `load_composer_authority.py:37` lo justifica como *"self-contained … sin depender de osap-api"*.
2. **Tres semánticas de acentos distintas** (y ya causó drift real):
   - `encode("ascii","ignore")` **borra** lo no latino: `osap-api/domain/normalization.py:9`, `canonicalizer.py:20`, `index_works.py:137`; `osap-storage` scripts `link_import_by_identity.py:38`, `resolve_persons.py:41`, `merge_duplicate_persons.py:70`…
   - `if not unicodedata.combining(ch)` **conserva** la letra base (cirílico incluido): `composer_names.py:24`, `osap-api/music_query_normalizer.py:16`.
   - `NFKC` **compone** en vez de descomponer: `link_works_person_import.py:56`.
   - Prueba del fallo: `scripts/normalize_identity_names.py` tuvo que recalcular **96.730 filas** de `persons_identity.identity_name_norm` porque `composer_key` conservaba diacríticos.
3. **`composer_key` ≠ `normalize_composer_name` dentro de `osap-storage`**: la primera tokeniza con `[a-z\u00e0-\u00ff]+` (pierde cirílico/CJK) y colapsa a *iniciales apellido*; la segunda conserva alfabetos y no colapsa.
4. **Catálogos con 3–4 extractores paralelos**: `domain/entities/catalogue.py` + `application/use_cases/catalogues.py`, regex inline en `scripts/import_cpdl_works.py:115`, y en `osap-api` `index_works.py:131,216` / `index_catalog_provider.py`.
5. **Tests**: sólo cubren la función canónica (`tests/domain/test_composer_normalization.py`, `tests/application/test_composer_review.py`, `osap-api/tests/osap/test_canonicalizer.py`). Ninguna copia local tiene test.

**Recomendación (alcance de la revisión de consolidación):**
- Una única `normalize_person_name` (misma semántica de acentos) y una única `composer_identity_key`, compartidas o replicadas 1:1 con test de contrato cruzado.
- Decidir si los no-latinos se conservan o se descartan, uniformemente (afecta a `persons_identity`, `persons_aliases`, `works_key`).
- Test que verifique que ambas apps producen la **misma** clave para Händel/Müller/Fauré y un nombre cirílico/CJK.
- Los scripts de un solo uso pueden conservar copias, pero marcadas y sin divergir del canónico.

**Riesgo**: medio. No rompe nada hoy, pero mientras existan criterios distintos la identidad de personas se puede volver a desalinear entre apps (ya pasó una vez).

---

## 12. CPDL: género y ediciones (2026-09-17)

### 12.1 Género — mapeado
`scripts/map_cpdl_genres.py`. El corpus usa la taxonomía coral de ChoralWiki (776 valores);
se reduce a los 12 géneros con reglas explícitas + palabras clave.

| Género | Obras |
|---|---|
| Música Sacra / Himnología | 36.979 |
| Música Clásica / Docta | 21.185 |
| Tradición Folclórica | 1.519 |
| Música Escénica / Aplicada | 906 |

- **60.589** filas en `work_genres`; 56.300 de 56.420 obras con género (120 sin etiqueta útil).
- Mapeo auditable en `genre_mappings` con prefijo `cpdl:` (765 códigos). Fuera sólo
  `unknown`/`other`/`dual`/`both` (ruido).

### 12.2 Ediciones y ficheros — modelo nuevo
Esquema `scripts/migrate_cpdl_editions.sql`, poblado por `scripts/import_cpdl_editions.py`.
Modelo acordado: **Obra → Ediciones CPDL → Ficheros**, con **Editor (persona, rol 6)** sobre
la edición. No se duplican filas en `works`.

- `cpdl_editions`(id, works_id, cpdl_editions_cpdlno, cpdl_editions_license, created_at) —
  conserva el **CPDLno** y la licencia (un `{{Copy}}` por edición; hay ediciones sin ficheros).
- `cpdl_edition_files`(id, cpdl_editions_id, name, type, created_at).
- `cpdl_edition_persons`(id, cpdl_editions_id, persons_id, roles_id=6, name, created_at).
- `n_editions`/`n_files` son **derivables** (`COUNT`), sin contadores materializados.

Poblado: **81.983 ediciones** en **56.179 obras**, **217.343 ficheros** (PDF 75.250, MXL 60.948,
MIDI 44.850, MP3 10.267, CAPX 9.030, MUS 8.465, SIB 6.399, MSCZ 2.115, MusicXML 19) y
**80.166** relaciones de editor (1.834 personas distintas; **1.296 personas nuevas** con rol 6).

Notas: el `cpdlno` **no es único** (48 duplicados reales: la misma edición listada en dos
páginas) y `cpdlno=0` se descartó como artefacto.

> **Modelo provisional (2026-09-18).** `cpdl_editions`/`cpdl_edition_files` se construyeron
> antes de fijar el nivel *representación*, y **no son la arquitectura definitiva**: están
> desconectados de la app (no los lee el buscador ni el provider) y no resuelven que las 56.420
> obras CPDL no tengan recursos. Se sustituirán por `representations` + `works_resources`
> (`Work → Representation → Resource`), absorbiendo también `archive_entries`/`works_type_file`.
> Detalle, mapeo y decisiones pendientes en
> **`docsNew/diseño-representaciones-recursos.md`**. No migrar ni retirar `archive_entries`
> hasta demostrar con consultas que su información queda cubierta. Datos: **11.242 ediciones sin
> ficheros** (10.902 con licencia, 10.198 con editor) y una edición con 225 ficheros (media
> 3,07) → validar el parseo antes de consolidar.

### 12.3 Instrumentación CPDL — cerrada
`scripts/map_instrumentation.py` ampliado para los textos libres de CPDL: conectores
(`, / & + and or with / e`), cantidades iniciales (`2 violins`), plurales, paréntesis
(se prueban el texto, sin paréntesis y cada paréntesis), calificativos (`ad lib.`,
`optional`, `reduction`, `colla voce`, tonalidad `in G`), numerales romanos (`Oboe I`) y
alias nuevos (`basso continuo`/`bc`, `violoncello`, `corni`, `classic guitar`, `hand drum`…).
Se añadió el instrumento genérico **Percussion** (cat. 3).

- **Residual: 795 → 126 obras** con texto instrumental real sin normalizar.
- Los 126 restantes ya **no son listas de instrumentos**: etiquetas sin instrumento (`Ad lib.`,
  `None`, `vocal`, `Other`), códigos de voces (`SATB.TTBB`, `SMATBarB`, `TrCTB`) y unas pocas
  frases descriptivas largas. Cierre aceptado.
- Totales tras el rebuild: `work_instruments` **337.110**, `work_voices` **30.962**,
  `work_ensembles` **96.305**. Origen PDMX: **0 textos sin mapear** (sin regresión).
- Backups de las 3 tablas antes del rebuild: `%TEMP%\kilo\instrumentation_pre_*.sql`.

Atribución (compositor de 153.579 obras) sigue en el módulo de identidad/datos.

