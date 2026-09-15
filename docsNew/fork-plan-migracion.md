# Plan de migración del aplicativo a la nueva BBDD

Estado: `osap-storage` = nueva (44 tablas, 310.455 works) · `osap-storage_v1` = antigua · rama `fork-new-db`.

---

## 1. Explicación de la atribución actual

| Dato | Valor |
|---|---|
| `persons` | 2.278 |
| Personas con rol 1 (compositor) | 1.771 |
| **Personas sin ninguna obra** | **507** |
| Relaciones rol 1 (`works_person_roles`) | 52.182 |
| Obras con compositor | 50.379 |
| Obras totales | 310.455 |
| **Obras sin compositor** | **260.076** (229.561 PDMX + 30.515 CPDL) |

Tu lectura es correcta: **507 compositores sin obras** y **260.076 obras sin compositor**. Por qué:

1. Las 2.278 personas son las migradas de `osap-storage_v1.composers` (el catálogo real). **No se ha creado ninguna** (se revirtieron las 33.919 que se crearon).
2. En `_v1`, solo **244** compositores tenían `works.composer_id`; el resto es catálogo sin obras asignadas.
3. Al cruzar por nombre/alias el texto de `works.composer` contra las personas existentes, subieron a **1.771** los que tienen obra → quedan **507** sin ninguna.
4. Las 260.076 obras sin compositor son:
   - **171.249** PDMX con `composer = 'NA'` (sin atribución en origen),
   - **~58.000** PDMX con texto que **no** casa con ninguna persona del catálogo,
   - **30.515** CPDL sin compositor o sin casar.
5. Estas dos bolsas (507 sin obra / 260.076 sin compositor) son exactamente lo que resolverá el **fichero de compositores bajo estudio**. Hasta entonces, el listado de compositores es "personas con rol 1" (1.771).

---

## 2. Punto de partida del código

Ya hecho en `fork-new-db`:
- `sql_work_repository.py` (lectura/escritura base + `replace_*` + `get_lists_bulk`).
- `sql_composer_repository.py`: **camino de lectura** del admin (listado, conteos, detalle, obras) sobre `persons` + `works_person_roles` (rol 1).

Impacto restante: **80 ficheros** con referencias al esquema viejo. Top: `sql_composer_repository` (180), `composer_admin` (115), `tests/fakes.py` (111), `container.py` (60), `admin_composers` (48), `cli.py` (47).

Tablas del esquema viejo referenciadas por el código que **ya no existen** en la nueva:
`composers`, `composer_aliases`, `composer_authority`, `composer_authority_names`, `composer_biographies`, `composer_candidate`, `composer_evidence`, `composer_identifiers`, `composer_identity_resolution`, `composer_merge_history`, `composer_resolution`, `composer_statistics`, `cpdl_pages`, `cpdl_voicings`, `authority_identifiers`, `authority_sync_state`, `catalogues`, `works_instruments`, `work_tags` (ahora `work_tag`), `musicbrainz_cache`.

Equivalencias:
| Viejo | Nuevo |
|---|---|
| `composers` | `persons` |
| `composer_aliases` | `persons_aliases` (`person_id`) |
| `composer_biographies` | columnas `persons_biography_*` de `persons` |
| `composer_identifiers` | `persons_identifiers` (`persons_id`) |
| `composer_evidence` | `persons_evidence` |
| `composer_merge_history` | `persons_merge_history` |
| `composer_authority` / `_names` | `persons_authority` / `persons_authority_name` |
| `works.composer_id` | `works_person_roles` (rol 1) |
| `works.genre` / `work_genres.genre` | `work_genres` + `genres` (vía `genre_mappings`) |
| `works.instrumentation` / `work_instruments.instrument` | `work_instruments` + `instruments` (+cantidad) |
| `works.tags` / `work_tags` | `work_tag` + `tag_work` |
| `works.language` | `work_language` + `languages` |
| `cpdl_pages` | `works` (`origin='CPDL'`, `origin_id`, `works_voicing`, `works_instrumentation`) |
| `cpdl_voicings` | `voices`/`work_voices` + `ensembles`/`work_ensembles` |
| `catalogues` | `catalog` |
| `composer_candidate` / `composer_identity_resolution` / `composer_resolution` / `composer_statistics` | **abandonados** (borrar código) |

---

## 3. Fases

### Fase 1 — Persistencia (repositorios, entidades, puertos)
1. `sql_composer_repository.py`: terminar los ~35 métodos restantes (alta, alias, identificadores, evidencia, biografía, merge, review, atribución, resolución, backfill, prune, unknown).
2. `sql_voting_repository.py` (`votes`/`work_statistics`), `sql_catalogue_repository.py` (`catalog`), `sql_authority_*` (`persons_authority*`), `sql_job_repository`, `sql_statistics_repository`.
3. `domain/entities/composer.py` + `domain/ports/composer_repository.py`: decidir si `Composer` pasa a `Person` (o se mantiene el nombre con campos `persons_*`) y ajustar puertos.
4. `domain/entities/work.py`: exponer `origin`, `origin_id`, `voicing` y las relaciones (voces/ensembles) si el contrato las necesita.
5. `infrastructure/container.py` (60 refs): rewire de repos/use cases retirados.

**Hecho cuando**: no queda ninguna referencia a `composer_*`/`composers`/`cpdl_*` en `infrastructure/` y `ruff`+`pytest` pasan.

### Fase 2 — Personas/compositor (use cases)
1. `application/use_cases/composer_admin.py` (115 refs) + `api/routes/admin_composers.py` + `api/web/admin_composers_crud.py`.
2. `populate_composers.py`, `composer_recovery.py`, `musicbrainz_enrich.py` (usa `composer_identifiers`/`composer_evidence`), `composer_review_ai.py`.
3. **Retirar** los flujos abandonados: candidatos, resolución/identity_resolution, estadísticas de compositor (y sus endpoints/scripts/tests).
4. Decidir la política de atribución: listar solo personas con rol 1; el alta/creación de personas queda **bloqueada** hasta el fichero bajo estudio.

### Fase 3 — Ingesta
1. `build_works.py` (register-works): crear `works` + `works_person_roles` (rol compositor) en vez de `composer`/`composer_id`; `work_key`.
2. `import_pdmx.py`, `register_file.py`, `register_resources.py`, `materialize_*`, `resolve_file.py`, `stream_file.py` (almacenamiento; esquema igual salvo nombres).
3. `enrich_metadata.py`: escalares a `works_*`; `replace_*` ya adaptado; `genre`/`instruments`/`tags` a las junctions nuevas.
4. CPDL: reescribir `api/routes/cpdl.py` + `application/services/cpdl_voicing.py` sobre `works_voicing`/`voices`/`ensembles`, o retirarlos si el corpus CPDL ya es `works`.

### Fase 4 — API y web
1. `api/routes/provider.py` + `api/schemas.py`: DTO con compositor/artista desde personas, instrumentación desde `work_instruments`, género desde `work_genres`, voicing/ensembles.
2. `api/routes/composers.py`, `works.py`, `admin_works.py`, `admin_composers.py`, `web/*`.
3. `tests/api/test_provider_contract.py` y `tests/fakes.py` (111 refs) actualizados al nuevo modelo.

### Fase 5 — CLI y scripts
1. `infrastructure/cli.py` (47 refs): comandos `register-works`, `enrich-metadata`, `populate-composers`, `sync-authority`, `musicbrainz-enrich`, `recompute-statistics`...
2. `scripts/`: actualizar los que apuntan a `--db osap-storage_new` (ahora `osap-storage`) y retirar los de flujos muertos (`candidate_*`, `incorporate_resolutions`, `composer_review_ai`, `verify_omr_*` si aplica).

### Fase 6 — Migraciones y arranque
1. Retirar/archivar `infrastructure/db/migrations/001..041` (esquema viejo) y definir el runner del fork sobre el esquema actual (¿baseline + futuras?).
2. `bootstrap` (provider por defecto) y health checks contra el nuevo esquema.

### Fase 7 — CRUDs completos (al final, como pediste)
1. **Un CRUD completo por tabla** (no el CRUD genérico): listado, ficha, búsqueda/filtros, paginación, enlaces entre tablas relacionadas, controles de alta/edición/borrado y validación.
2. Cubrir las 45 tablas del esquema nuevo (las uniones N:N con PK compuesta, con su propia UI: p. ej. `work_instruments` con cantidad, `work_voices` con contexto, `work_ensembles`).
3. `sql_table_crud_repository.py` (whitelist ya actualizada al esquema real) queda como base para listados genéricos, no como producto final.

### Fase 8 — Validación
1. Tests de integración contra la BBDD real: **ya creados** en `tests/integration/test_sql_repositories.py` (se activan con `OSAP_TEST_DB=1`; validan la whitelist contra `information_schema`, works, personas con rol 1, estadísticas y catálogo).
2. Contrato del provider (v1.3) end-to-end con datos reales.
3. Comprobaciones de recuento (obras/compositor, listados, descargas).

---

## 4. Decisiones pendientes

1. **Atribución de compositores**: el alta/resolución de nombres queda bloqueada hasta estudiar el fichero; ¿se permite crear personas entonces o solo enlazar existentes?
2. **Flujos abandonados** (candidatos/resolución/estadísticas): confirmar borrado de código, endpoints, scripts y tests.
3. **`Composer` → `Person`** en el dominio: renombrar entidad/puertos o mantener alias.
4. **CPDL**: ¿se mantiene el endpoint de búsqueda por voicing sobre `works_voicing`, o se retira?
5. **Runner de migraciones** del fork.
6. **CRUD genérico**: whitelist definitiva.

---

## 5. Orden recomendado y criterio de "hecho"

1. Fase 1 (bloquea todo lo demás) → `ruff` + `pytest` verdes y sin refs a `composer_*` en infraestructura. **HECHA** (2026-09-15): repositorios adaptados, flujos abandonados retirados (`authority_identifiers`, `musicbrainz_cache`, `authority_sync`, `ingest_authority`), `authority_sync_state` creada, whitelist del CRUD actualizada, tests de integración añadidos (7 pasan contra la BBDD real).
2. Fase 3 (ingesta) para poder reconstruir datos con el fork.
3. Fase 2 (personas/compositor) y retirada de flujos muertos. **En curso**: `scripts/link_works_person_import.py` (normaliza/compacta `works_person_import` y enlaza con `persons`/`persons_aliases` **sin crear personas**; 42.066 filas casadas de 136.888, 91.819 sin coincidencia, 3.003 ruido).
4. Fase 4 (API/web) + contrato.
5. Fases 5-6 (CLI/migraciones).
6. Fase 7 (un CRUD completo por tabla).
7. Fase 8 (validación end-to-end contra la BBDD real; ya hay base de integración).

Riesgo principal: los tests actuales usan fakes, así que **no detectan errores de SQL**; conviene montar cuanto antes un test de integración contra `osap-storage` para validar cada repositorio adaptado.

---

## 6. Estado de datos (2026-09-15)

**`works_person_import`: CERRADO de momento.**

| Concepto | Valor |
|---|---|
| Personas (`persons`) | 38.492 (35.508 `source_system='pdmx'`, 706 `'authority'`) |
| Personas con rol 1 (compositor) | 26.881 — **todas con ≥1 obra** |
| Personas con rol 10 (intérprete) | 17.789 |
| Relaciones rol 1 / rol 10 | 122.381 / 74.669 |
| Obras con compositor | 117.189 |
| `works_person_import` resueltas | 187.554 |
| Pendientes **composer** | 19.909 (placeholders: `Misc`, `after X`, mojibake…) |
| Pendientes **artist** | 163.963 (placeholder `Misc tunes` = 142.879, más single-token/odd) |
| Personas sin ninguna obra | 485 → **`persons_visible = 0`** |

**PENDIENTE IMPORTANTE: localizar el compositor de 193.266 obras** (de 310.455, el 62%).
Son las obras que quedan sin relación de compositor (PDMX con texto `NA`/no-persona y CPDL sin compositor). Las vías ensayadas: autoridad (agotada), búsqueda web (lenta: ~16 filas/min), `works_person_import` (agotado). Siguiente vía razonable: metadata de MuseScore (`data.score.composer_name`, local) y APIs Wikipedia/IMSLP.

### Pasos siguientes (fases)
- **Fase 2 (en curso)**: use cases de personas/compositor (`composer_admin.py`, `populate_composers.py`, `composer_recovery.py`) y rutas `admin_composers`/`composers`.
- **Fase 3**: ingesta (`build_works`, `import_pdmx`, `enrich_metadata`, CPDL).
- **Fase 4**: contrato del provider + DTOs.
- **Fase 5-6**: CLI/scripts y migraciones.
- **Fase 7**: un CRUD completo por tabla.
- **Fase 8**: validación (ya hay 8 tests de integración en verde).
