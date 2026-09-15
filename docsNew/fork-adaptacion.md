# Fork `osap-storage` → nueva BBDD

Rama: **`fork-new-db`** (parte de `main`; `main` queda intacto).
Objetivo: adaptar el aplicativo al esquema de `osap-storage_new` (que será `osap-storage`).
Prioridad: **proceso** (ingesta/lectura pública) antes que **CRUD genérico** (dejado para el final).

## Cambios de esquema que afectan al código

| Antes (viejo) | Ahora (`_new`) |
|---|---|
| `works.composer`, `composer_id`, `artist` | `works_person_roles` + `persons` (rol 1 = Composer, 10 = Intérprete) |
| `works.genre` (texto) | `work_genres` + `genres` (vía `genre_mappings`) |
| `works.instrumentation` (texto) | `work_instruments` + `instruments` (+ `work_instruments_quantity`) |
| `works.tags` (texto) | `work_tag` + `tag_work` |
| `works.language` | `work_language` + `languages` |
| `works.work_key` | `works.works_key` |
| `works.relative_path`, `title`, `subtitle`, `opus`, `catalogue`, `musical_key`, `year`, `duration`, `measures`, `pages`, `parts`, `complexity`, `license`, `public_domain`, `description` | mismas con prefijo `works_*` (`works_relative_path`, `works_title`, ...) |
| `works.thumbnails` | desaparece |
| `cpdl_pages` / `cpdl_voicings` | `works` (`origin='CPDL'`, `origin_id`=id página, `works_voicing`) + `voices`/`work_voices` + `ensembles`/`work_ensembles` |
| `composers` / `composer_*` | `persons` / `persons_*` |

## Fases

### Fase 1 — Persistencia base (hecho parcialmente)
- [x] `infrastructure/repositories/sql_work_repository.py` adaptado: lectura (`get_by_id`, `get_by_work_key`, `search`, `list_all`, `list_by_composer`, `count`), `create`/`update` con columnas `works_*`, `replace_tags/genres/instruments/parts` y `get_lists_bulk` contra las tablas nuevas.
- [ ] `sql_composer_repository.py` → `persons_*` (y roles).
- [ ] `sql_voting_repository.py`, `sql_catalogue_repository.py` (catálogos → `catalog`), `sql_authority_*` (`authority_*`), `sql_job_repository`, `sql_statistics_repository`.
- [ ] `domain/entities/work.py`: valorar exponer `origin`, `origin_id`, `voicing`, `voices`/`ensembles` (hoy no están en la entidad).

### Fase 2 — Proceso de ingesta (antes que el CRUD)
- [ ] `application/use_cases/build_works.py` (register-works): debe crear `works` + `works_person_roles` (compositor) en vez de `composer`/`composer_id`.
- [ ] `application/use_cases/enrich_metadata.py`: los campos escalares ya van a `works_*`; `genre`/`instruments`/`tags`/`parts` ya se vuelcan vía `replace_*`.
- [ ] `application/use_cases/import_pdmx.py` y `resolve_file`/`stream_file` (almacenamiento: `archive_entries`/`files`/`storage_locations` se copian igual).
- [ ] CPDL: retirar `api/routes/cpdl.py`/`application/services/cpdl_voicing.py` o reescribirlos sobre `works_voicing`/`voices`/`ensembles`.
- [ ] `scripts/backfill_cpdl_voicings.py` y demás scripts que apuntan al esquema viejo.

### Fase 3 — Contrato público y admin
- [ ] `api/routes/provider.py` y DTOs: compositor/artista desde personas; instrumentación desde `work_instruments`; género desde `work_genres`; voicing/ensembles.
- [ ] `api/routes/works.py`, `composers.py`, `admin_works.py`, `admin_composers.py`, web (`api/web/*`).
- [ ] **CRUD genérico** (`sql_table_crud_repository.py` whitelist + `api/routes/admin_*`): al final, con la whitelist del esquema nuevo.

### Fase 4 — Migraciones y arranque
- [ ] Decidir el runner de migraciones del fork: `osap-storage_new` ya tiene el esquema aplicado; las migraciones 001–041 (esquema viejo) no aplican.
- [ ] `infrastructure/db/migrations/`: 035/036 (cpdl_pages/cpdl_voicings) quedan obsoletas.

## Estado
- Rama `fork-new-db` creada. `scripts/import_cpdl_pages.py` retirado.
- `sql_work_repository.py` adaptado y validado (`ruff` OK, `tests/api/test_provider_contract.py` 7/7 con fakes).
