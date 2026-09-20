# Informe de migración — `osap-storage` (rama `fork-new-db`)

Fecha: **2026-09-20**. Alcance: estado de la migración del aplicativo legacy (`_v1`) al esquema
nuevo (`osap-storage`), fases 1-8 del `fork-plan-migracion.md`, con cifras **verificadas en vivo**
contra `osap-storage` el 2026-09-20.

---

## 1. Resumen ejecutivo

| Área | Estado |
|---|---|
| Persistencia (repos/entidades/puertos) contra el esquema nuevo | ✅ Cerrada |
| API + web contra la BBDD real (no fakes) | ✅ Validada end-to-end |
| CLI y scripts (sin flujos muertos, sin refs al esquema viejo) | ✅ Cerrada |
| Migraciones (baseline + runner `schema_migrations`) | ✅ Cerrada |
| Módulo `persons` | ✅ Cerrado (núcleo) · 🔄 limpieza de nombres en curso (§5.5) |
| Módulo `works` | ✅ Cerrado |
| Módulo `representations` / `resources` (datos) | ✅ Cerrado sin transformación estructural |
| Materialización CPDL (ficheros) | ⏸️ Decisión de producto/licencia, posterior |
| Fase 7 (un CRUD por tabla) | 🔄 En curso (`representations` cerrado; `resources` backend listo) |
| Atribución de compositor de obras sin autor | 🔄 Vía RISM en curso, acotada |

**Calidad**: `ruff` limpio · **298 tests** en verde (unit + integración) · frontend `tsc`+`vite`
limpios · cadena `work → representation → resource` probada desde `osap-api`.

---

## 2. Estado de datos (verificado 2026-09-20)

### 2.1 Obras y atribución

| Dato | Valor |
|---|---|
| `works` | **310.455** |
| Obras con compositor (rol 1) | **135.315** |
| Obras sin compositor (rol 1) | **175.140** |
| Relaciones rol 1 / rol 10 (`works_person_roles`) | **136.256** / **75.419** |
| `works_song_name` vacío | **1.361** |
| `persons` | **45.217** |
| Personas visibles / ocultas | **44.524** / **693** |
| Personas con rol 1 | **31.758** |
| Personas sin obra (rol 1) | **13.459** |
| `persons_identity` / `persons_aliases` | **114.194** / **47.997** |

### 2.2 Representaciones y recursos (modelo Work → Representation → Resource)

| Dato | Valor |
|---|---|
| `representations` | **81.983** (todas `origin='cpdl'`, `type='edition'`) |
| Representaciones con ≥1 recurso | **70.741** |
| Representaciones sin recurso (inventario) | **11.242** |
| `representation_persons` (editores, rol 6) | **80.166** |
| `works_resources` | **471.378** |
| · con `file_id` (internos, descargables) | **254.035** (PDMX) |
| · con `url` externa derivada | **217.343** (CPDL) |
| · con representación / sin representación | **217.343** / **254.035** |
| Obras con recursos | **303.923** |
| Recursos huérfanos (`work_id` inexistente) | **0** |
| Duplicados `file_id` / `(representación,nombre,tipo)` | **0** / **0** |

Tipos: MXL 314.983 · PDF 75.250 · MIDI 44.850 · MP3 10.267 · CAPX 9.030 · MUS 8.465 · SIB 6.399 ·
MSCZ 2.115 · MusicXML 19.

### 2.3 Índice externo RISM (no integrado en `works`)

`rism_sources` **1.565.667** (+ `rism_source_links` 701.553 enlaces `856$u`) — tabla externa de
autoridad/evidencia (**decisión op2**), no corpus de `works`.

---

## 3. Modelo canónico fijado

```
works ── representations ── representation_persons      (CPDL: work → edición → N recursos)
                    └────── works_resources
works ── works_resources (work_id)                      (PDMX: work → recurso 1:1, sin representación)
```

- **PDMX**: `work → resource` directo (1:1 con `files`).
- **CPDL**: `work → representation (edition) → resources` (2,65 ficheros/edición de media).
- **Representation** y **Work** son niveles de **resolución por agrupación**; **sin nuevo nivel
  persistente** (decisión D3=A).
- RISM **no** entra en `works` (solo identificación/evidencia).

### Legado conservado (sin transformar, con consumidores o por compatibilidad histórica)

`archive_entries` (PDMX), `cpdl_editions`, `cpdl_edition_files`, `cpdl_edition_persons` (staging
CPDL), `works_obra_iden` (0 usos, 0 valores). **No se eliminan ahora**: el objetivo es explotación,
no limpieza estética del esquema.

---

## 4. Fases (plan de migración)

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Persistencia: repositorios, entidades, puertos, whitelist CRUD | ✅ 2026-09-15 |
| 2 | Personas/compositor: use cases, rutas, retirada de flujos abandonados | ✅ (módulo `persons` cerrado) |
| 3 | Ingesta: `build_works`, `import_pdmx`, `enrich_metadata`, CPDL | ✅ operativa (pendiente menor de instrumentación) |
| 4 | API y web + contrato del provider | ✅ validada contra BBDD real |
| 5 | CLI y scripts | ✅ |
| 6 | Migraciones y arranque | ✅ |
| 7 | Un CRUD completo por tabla | 🔄 en curso |
| 8 | Validación end-to-end | ✅ base ampliada (integración + cadena `osap-api`) |

### Fase 4 — validación API (2026-09-18)

- **34/34** endpoints GET · **10/10** rutas HTML · **7/7** desplegables de relaciones de obra.
- Bugs reales corregidos: `files.sha256` NULL en 254.035 filas (`FileRead.sha256: str | None` y
  `domain/entities/file.py`); `/api/admin/works` 500 por `_to_detail` sin aplanar
  (`dataclasses.asdict`).
- Aislamiento de tests: `tests/conftest.py` con `monkeypatch` (antes se filtraba `OSAP_CONFIG`).

### Fase 5-6 — CLI/scripts y migraciones (2026-09-19)

- `infrastructure/cli.py`: los **23** atributos de `Container` existen; sin comandos de flujos
  abandonados (`sync-authority`, `candidate`, `resolution`).
- **0** referencias a `osap-storage_new` en scripts.
- Retirados 5 scripts muertos (reversibles vía git): `composer_review_ai.py`,
  `incorporate_cpdl_composers.py`, `incorporate_from_authority.py`, `resolve_composers_web.py`,
  `verify_omr_representations.py`.
- Esquema viejo archivado en `infrastructure/db/migrations_v1/` (40 ficheros); baseline en
  `infrastructure/db/migrations/001_baseline_schema.sql` + runner `infrastructure/db/migrate.py`;
  `schema_migrations` = **1 fila**.

---

## 5. Módulos cerrados

### 5.1 `persons` (2026-09-19)

- **Fusión identidad**: `persons_authority*`/`persons_identifiers` → `persons_identity` (EAV;
  canónica + candidatos + ids). Alias de autoridad → `persons_aliases`.
- **Lote 1A**: 7 merges de prefijados (`Arranged from …`/`From …`) con `persons_merge_history` +
  snapshots; ciclo `apply → verify → revert → verify → apply → verify` correcto.
- **404 prefijados** clasificados: 50 duplicado seguro (7 hechos) · 115 variante (review) ·
  68 sin destino (rename candidato) · 164 no-persona · 4 ambigua · 3 descartado.
- **Sin merges automáticos seguros pendientes**; sin referencias rotas.
- Corrección aplicada de la persona Haydn mal fusionada (`persons_correction_history`).
- **Reabierto el 2026-09-20** por calidad de los nombres importados del texto de obra; ver §5.5.

### 5.2 `works` (2026-09-19)

- **`works_person_import` → `works_person_roles`**: **2.540** materializaciones (1.790 rol 1 + 750
  rol 10) auditadas en `works_person_roles_history`, reversibles; 0 colisiones; ninguna persona
  nueva.
- **`works_song_name`**: **70.370 A + 87 B/A aplicados** (total rellenado **70.457**), **191 B
  preservados**, **1.170 C en revisión**. Reversible vía `works_field_history`
  (`operation='fill'|'strip'`); restan **1.361** vacíos.
- **`works_obra_iden`**: 0 referencias en código y 0 valores → legacy cerrado (se conserva
  físicamente).

### 5.3 `representations` / `resources` (2026-09-19)

- Diagnóstico + cierre estructural sin transformación; modelo canónico fijado.
- **CPDL URLs activadas**: `works_resources_url` = `…/Special:FilePath/<nombre URL-encoded>` para
  **217.343** recursos, con `works_resources_field_history` (`operation='derive_url'`); ciclo
  `apply → revert → re-apply` verificado. No se descargó ni rehospedó nada.

### 5.4 Corrección del root de almacenamiento (2026-09-20)

El corpus PDMX está rehospedado en disco (**254.035** `.mxl`, **1,85 GB** en
`G:\osap-storage\mxl`; `files` y `storage_locations` = 254.035, `status='stored'`), pero el
proveedor `local` apuntaba a `G:/osap-storage/files` (**inexistente**): `0/4.000` `object_key`
resolvían, y `GET /api/v1/files/{id}/content` devolvía **404** (el CDN no estaba afectado).

Corregido a `G:/osap-storage` en `osap-storage`, `osap-storage_test` y
`config.yaml` (`repository.local.root`). Verificado: streaming local **200** con bytes
(4 `file_id`), cadena `/api/download/{id}` → 302 → CDN → **200** (3 recursos), `ruff` limpio,
**298 tests** en verde. Detalle y revert en `docsNew/correccion-root-storage.md`.

### 5.5 Limpieza de nombres de `persons` (2026-09-20)

Reapertura de `persons` por la calidad de los nombres que entraron desde el texto de obra (PDMX):
**988 filas sospechosas** de 45.217 (diagnóstico en `docsNew/diagnostico-persons-limpieza.md`,
inventario en `G:\rism\persons_limpieza_dry_run.csv`).

**Fase 1 aplicada y verificada** (`scripts/cleanup_persons_phase1.py`, dry-run por defecto,
`--apply`, `--revert <batch>`; auditoría en `persons_correction_history`):

| Acción | Filas |
|---|---|
| `ocultar` (`persons_visible = 0`) | **216** |
| `renombrar` (quitar prefijo `:`/`'`/`?` y arreglar fechas) | **10** |
| diferido (pares pegados, bloques de crédito con 2-3 personas) | **10** |
| placeholders → `works_attr_type` | **4** |

Visibles 44.740 → **44.524** · ocultas 477 → **693**. Ciclo `apply → verify → revert → verify →
apply → verify` correcto. Casos resueltos: los ejemplos que parecían ausentes estaban en inglés
(`¿Número 12?` = `'No 12'`, `¡¡Vaya a la configuración!!` = `!! Go to stettings`,
`¿Banda de pasas?` = `?Raisin Band?`).

**Criterio de ensembles (fijado)**: una banda/ensemble **con nombre propio es un artista** y se
queda en `persons` (`Zac Brown Band`, `The Dave Brubeck Quartet`, `Electric Light Orchestra`…,
roles 1/10). `ensembles` es un catálogo de **tipos/configuraciones** vocales (`ensembles_code`
UNIQUE + `ensemble_voices`: `SATB`, `SSAA`, `BAND`…), no de agrupaciones con nombre; un intento de
moverlas se detectó, se abortó sin estado parcial (360/96.305 intactos) y se revirtió el DDL
asociado.

**Codificación**: la BBDD y la conexión son `utf8mb4`; el cirílico/chino correcto se almacena bien.
Las **244** filas mojibake perdieron bytes en el import y **no** se recuperan reinterpretando la
cadena (3/244) → hay que releer el nombre de la fuente.

---

## 6. Cambios de código relevantes

| Área | Cambio |
|---|---|
| Modelo | `scripts/migrate_representations_resources.sql` + `scripts/migrate_to_representations.py` (idempotentes, `COLLATE utf8mb4_unicode_ci`) |
| Lectura | `RepresentationRepository` consumido por `GetWork` / `SearchWorksFull` |
| DTO provider | Bloque `representations` (aditivo) |
| Descarga | Resolución por `resources.id` (interna PDMX / 302 externa CPDL) |
| Renombrado | `Composer` → `Person` (`domain/entities/person.py`, `PersonRepository`) con re-exports de compatibilidad; `composer_id` → `person_id` propagado a `osap-api` |
| Resolutor | `GET /api/admin/resolution/works/{id}` (solo lectura, sin persistencia) |
| Fase 7 | `admin_representations.py` + `admin_resources.py` + repos admin + use cases + schemas; `representation_admin`/`resource_admin` en `container.py` y `dependencies.py` |
| Frontend | `Representations.tsx` + ruta `/representations`; cliente API de `resources`; fallback SPA `/admin/{path}` |

---

## 7. Reversibilidad y auditoría

Toda mutación de datos deja historial con `operation` y `batch_id`:

| Tabla de historial | Filas |
|---|---|
| `works_field_history` (song_name fill/strip) | **70.457** |
| `works_resources_field_history` (derive_url) | **217.343** |
| `works_person_roles_history` (assign WPI) | **2.540** |
| `persons_merge_history` (+ `persons_merge_snapshot`) | **3.247** |
| `work_attribution_history` (`operation='assign'`, RISM) | **136** |
| `persons_correction_history` (Haydn + limpieza de nombres) | **721** |

Metodología aplicada en cada bloque: **diagnóstico → dry-run → ejecución auditable → verificación
(`apply → verify → revert → verify → apply → verify`) → informe de cierre**.

---

## 8. Verificación

- `ruff check .` limpio.
- **298 tests** en verde (unit + integración) con
  `OSAP_TEST_DB=1`, `OSAP_TEST_DB_NAME=osap-storage_test`.
- Contratos de repositorio contra el esquema real (`tests/integration/test_repository_contracts.py`)
  y contratos de API (`tests/integration/test_api_contracts.py`, 17 tests: listado/ficha y
  round-trip de `representations` y `resources`).
- Cadena end-to-end desde `osap-api`:
  - **PDMX**: `OmrStorageFetcher` → `/api/search` → 50 works, recurso MusicXML con
    `/api/download/{id}`.
  - **CPDL**: `/api/search?corpus=cpdl&q=dido` → 20 works con representación, descarga
    `/api/download/293739` → **302 a `Special:FilePath/dido_and_aeneas_-_full_score.mxl`**.

---

## 9. Pendientes

1. **Fase 7 (en curso)**: UI dedicada de `resources` (backend + cliente API hechos); después
   `persons`, `works` y las uniones N:N.
2. **Materialización CPDL (opción b)**: rehostear/descargar los 217.343 recursos → decisión por
   licencia de edición.
3. **`works_song_name` C (1.170)** y **191 B** preservados → revisión semántica dirigida.
4. **Normalizar `works_instrumentation` (56.420 filas) → `work_instruments`**.
5. **sha256**: `files.sha256` vacío en 254.035 filas (no calculado en este entorno) → calcular y,
   cuando exista, eliminar `works_music_digest` (a 0).
6. **Atribución de las 175.140 obras sin compositor**: vía RISM acotada (guardas + revisión manual;
   52 títulos revisados → 44 accept/124 obras, 6 reject, 2 review; enlace por VIAF aplicado en
   BATCH2). Restan: personas `from/Arranged from`, `sin_identidad`, 394 `inferred`.
7. **Autoridad de títulos de obra**: decidir título canónico (probablemente `works_song_name`) y si
   se añade tabla de alias de título.
8. **Jobs de refresco CPDL/RISM** (idempotentes, con conteo).
9. **Limpieza**: directorio físico de ficheros consolidado y retirada final de `cpdl_*` /
   `archive_entries` **solo** tras repetir las comprobaciones de integridad.
10. **Reconciliación del proveedor de almacenamiento**: `ensure_default_provider` no actualiza
    `config` si el proveedor ya existe → conviene una comprobación de salud que valide que el
    `root` existe y que una muestra de `object_key` resuelve a fichero real.
11. **`persons` — placeholders (4 filas, 2.015 obras)**: marcar la **obra** con `works_attr_type`
    (`TRADICIONAL` / `ATRIBUIDA`) + `works_attribution_note` y no usar persona; después ocultar las
    4 personas placeholder.
12. **`persons` — fase 2 (10 diferidos)**: dividir pares pegados y bloques de crédito
    (`Georges Bizet(18381875)arr. …`) decidiendo el rol por obra.
13. **`persons` — mojibake (244)**: releer el nombre de la fuente PDMX/MuseScore de la obra.
14. **`GET /api/v1/persons?role=…`** (multivalor: `composer,arranger`, `performer`, `editor`) con la
    regla de que `composer` devuelva solo quienes tienen **≥1 obra**.

---

## 10. Riesgos y observaciones

- **Cloudflare** impide validar por automatización la resolución real de las URLs CPDL
  (`urllib`/fetch → 403; navegador → reto). Se confirmó manualmente por el revisor.
- El desplegable de personas sirve ~45k opciones sin paginación ni búsqueda en servidor (mejora
  pendiente en Fase 7).
- Los tests unitarios usan fakes y no ejecutan SQL: la red de seguridad real son los tests de
  integración contra `osap-storage_test` (nunca contra la BBDD principal en pruebas que escriben).

---

## 11. Fuentes (documentación de cierre)

`fork-plan-migracion.md` · `cierre-persons.md` · `modulo-works-wpi.md` ·
`modulo-works-song-name.md` · `modulo-works-song-name-b.md` · `works-obra-iden-cierre.md` ·
`diagnostico-representaciones-recursos.md` · `cierre-representaciones-recursos.md` ·
`dry-run-cpdl-urls.md` · `cierre-fase5-6.md` · `fase7-crud-representations.md` ·
`diseño-semantica-representacion.md` · `diseño-resolutor-agrupacion.md` · `estudio-representations-vs-resources.md` · `correccion-root-storage.md` · `diagnostico-persons-limpieza.md`.
