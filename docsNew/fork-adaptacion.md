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
- [x] `sql_composer_repository.py` (camino de lectura del admin): `list_summaries`, `count`, `review_counts`, `list_suspicious`, `get_detail` y `list_works` sobre `persons` + `works_person_roles` **filtrando rol 1** (el listado de compositores son las personas con rol compositor).
- [ ] Resto de métodos de `sql_composer_repository.py` (aún con `composer_*`/`composer_id`): `create`, `get_by_id`, `get_by_name`, `find_by_identifier`, `list_aliases`/`add_alias`/`move_alias`/`promote_alias`, `rename_composer`, `update_composer`, `set_review_status`, `set_suspicious`, `set_musicbrainz_id`, `list_identifiers`/`add_identifier`/`delete_identifier`, `list_evidence`/`add_evidence`/`list_creation_evidence`/`add_creation_evidence`, `get_biography`/`upsert_biography`, `merge`, `set_attribution`, `resolve_by_normalized`/`resolve_many_by_normalized`, `list_pending_review`, `list_resolutions`/`record_resolution`, `backfill_creation_evidence`, `prune_zero_work_composers`, `ensure_unknown_composer`.
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
- **BBDD (2026-09-15)**: renombradas → `osap-storage` = nueva (44 tablas, 310.455 works), `osap-storage_v1` = antigua (42 tablas), `osap-storage_new` eliminada. `config.yaml` sigue apuntando a `osap-storage`, así que la API usa ya la nueva al reiniciar.
- **Personas creadas revertidas**: se borraron las 33.919 `persons` con `persons_source_system='resolved'`. `persons` = 2.278; `works_person_roles` = 52.182 (1.771 personas con rol 1). La resolución de nombres queda pendiente con el fichero bajo estudio.
- **Pendiente**: listar compositores es "personas con rol 1 en `works_person_roles`" (ya aplicado en el camino de lectura); completar el resto de repositorios y use cases.
