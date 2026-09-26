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
3. Fase 2 (personas/compositor) y retirada de flujos muertos. **En curso**: `scripts/link_works_person_import.py` (normaliza/compacta `works_person_import` y enlaza con `persons`/`persons_aliases` **sin crear personas**; 42.066 filas casadas de 136.888, 91.819 sin coincidencia, 3.003 ruido). **Sub-fase CERRADA — concretización del modelo Person v1 (2026-09-22)**: entidad `Person` con `given_name`/`family_name`/`sort_name`/`nationality`/`image_url`/`person_type`/`attribution_note`; `PersonIdentifier` con `confidence`/`retrieved_at`; `SqlPersonRepository` y API actualizados; migración `006_person_model_refinement.sql` aplicada en MariaDB; verificado escritura→BBDD→lectura del circuito API/use case/repository. El **poblamiento** de esos campos (enriquecimiento) y el **circuito de atribución de obras** quedan como fases posteriores, fuera de este cierre. Ver `docsNew/modelo-persona-completo.md` §11.
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

---

## 7. Pendientes anotados (2026-09-16)

1. **`works_instrumentation` → `work_instruments`**: `works.works_instrumentation` guarda el
   texto/JSON crudo de instrumentación de CPDL (56.420 filas) y **se mantiene**. Falta un
   proceso que lo **normalice a `work_instruments`** (mapeando términos con `instruments`),
   como ya se hace con el enriquecimiento PDMX (`map_instrumentation.py`).
2. **SHA-256 / `works_music_digest`** — *prioridad baja (2026-09-17), en pendientes*:
   `files.sha256` está vacío en toda la BBDD (también en `osap-storage_v1`); el hash nunca se
   calculó en este entorno (lo produce `scripts/analyze_works_content.py` sobre los `.mxl` de
   `G:\osap-storage`). `works_music_digest` (clave de duplicados creada en la conversión) está
   a 0. Decisión: **calcular sha256 primero** y, cuando exista, **eliminar
   `works_music_digest`** (no aporta nada frente al sha256). Cuando se haga: re-ejecutar el
   script con `--only-missing` (ya tiene la query preparada con `music_digest IS NULL`).
3. **`work_person_roles_attribution_type`**: eliminada (estaba vacía, 0/212.999).
4. **Mantenimiento**: el **formulario de `works` con los 6 paneles de relaciones**
   (persona+rol, ensembles, genres, instruments, language, voices) está hecho
   (`api/routes/admin_work_relations.py` + `frontend/src/pages/WorkRelations.tsx`) y
   **validado end-to-end** el 2026-09-18 (ver §10).
5. **Modelo `Work → Representation → Resource`** (2026-09-18). Modelo **cerrado** y **migración
   paralela ejecutada** en `osap-storage_test` y `osap-storage`: `representations` **336.018**,
   `works_resources` **471.378**, `representation_persons` **80.166**; 0 huérfanos de `archive_entries`.
   `archive_entries` y `cpdl_*` intactos (transición aditiva). DDL
   `scripts/migrate_representations_resources.sql`, datos `scripts/migrate_to_representations.py`.
   La **app ya consume** el modelo nuevo (§12): GetWork/SearchWorksFull, DTO del provider
   (`representations`, aditivo), descarga por `resources.id` y whitelist CRUD. §11 **cerrado**
   (D1, D2, **D3=A**, D4) en **`docsNew/diseño-semantica-representacion.md`**: Representation y
   Work son niveles de **resolución por agrupación**; **sin nuevo nivel persistente**. Etapa
   siguiente: resolutor de agrupación, diseñado en
   **`docsNew/diseño-resolutor-agrupacion.md`** (criterios, autoridad de la identidad de obra,
   reglas aplicadas **y de bloqueo**, atributos comunes/divergentes) e **implementado** como
    resolutor de solo lectura (`GET /api/admin/resolution/works/{id}`, sin persistencia). Materialización CPDL y
    retirada de `cpdl_*`, aparte. No retirar `archive_entries` sin repetir las comprobaciones de §9.
6. **Autoridad de títulos de obra** (2026-09-19, pendiente). El nombre está repartido:
   `works.works_title` (presentación; **68.047** con `"título - compositor"`),
   `works.works_song_name` (**título limpio, 238.637 con valor** — la previsión original),
   `representations.source_name` (título de fuente, solo PDMX, 254.035, a menudo distinto de
   `works_title`), `works_resources.name` (ficheros) y `archive_entries.logical_id` (legacy).
   No hay tabla de alias de título (equivalente a `persons_aliases`) y la búsqueda solo usa
   `works_title` + catálogo + compositor. Decidir el **título canónico** (probablemente
   `works_song_name`) y si se añade `works_titles` (`main`/`source`/`uniform`/`alternative`)
   alimentada también desde `representations.source_name` y los títulos RISM `240`/`245`.
7. **Decisión RISM y forma del modelo** (2026-09-19, pendiente). RISM **no aporta ficheros**
   (solo ~12 % de fuentes con enlace a digitalización `856$u`); aporta **identificación** y
   `works_origin='rism'`. Medición estricta (`240` + persona canónica, sin anónimos ni genéricos):
   **356.811 obras RISM**, **78.016 ya en catálogo**, **278.795 nuevas** (match por título; cota
   superior). Fuente exportada: `G:\\rism\\rism_works_strict.csv` y `..._new.csv`. Si RISM se
   integra como corpus buscable en `works` → favorece **op1** (forma única `works`+`works_resources`,
   búsqueda conjunta); si queda como autoridad/evidencia → favorece **op2** (edición CPDL). Ver
   `docsNew/estudio-representations-vs-resources.md`.
   **Índice externo RISM completado (2026-09-19)**: `rism_sources` 1.565.667 (con `source_type`,
   `subjects`, `notes`, `institution_id`, `standard_title_id`, `other_persons`, `incipit_count` —
   2.457.350 incipits) + `rism_source_links` **701.553** enlaces `856` en **351.705** fuentes (22 %).
   De las 356.811 obras estrictas, **192.028 (54 %)** tienen ≥1 enlace a digitalización.
   **Decisión: op2** (representaciones solo para ediciones CPDL; RISM como tabla externa, no en `works`).
8. **Jobs de actualización CPDL/RISM** (2026-09-19, pendiente): preparar trabajos programados que
   refresquen `cpdl_*`/ediciones y el corpus RISM (`import_rism_sources.py` + `canonicalize_rism_persons.py`)
   según se actualicen las fuentes (idempotentes, con conteo y sustitución).
9. **Asignación de compositor/anónimo desde RISM** (2026-09-19, medido):
   - Compositores: viable pero acotado — 1.646 atribuciones usadas (281 `resolved` + 1.365 `inferred`),
     con **falsos positivos en repertorio tradicional** (God Save the King, Frère Jacques) → exige
     guardas (título tradicional, exigir `240`, rol no-copista) antes de escribir.
   - **Anónimos: no viable por título** — 50.813 fuentes RISM anónimas pero **0 con `240`** (sin
     título uniforme), así que 0 casan con nuestras obras; requeriría incipit/otros campos.
   - **Guardas + dry-run implementados (2026-09-19)**: `scripts/propose_rism_composers.py` →
     `docsNew/dry-run-rism-compositores.md` y `G:\\rism\\rism_composer_proposals.csv`. Guardas:
     `240` uniforme · un solo compositor · persona «Composer» · `Verified`/`Ascertained` · sin
     marcador tradicional. Resultado: **1.223 obras propuestas** (52 títulos `resolved` + 394
     `inferred`); bloqueados: 1.739 títulos por varios compositores (tradicional), 1.771 no-composer,
     394 baja fiabilidad. Sin escribir nada.
   - **Revisión manual (2026-09-19)**: 52 títulos `resolved` → **44 accept (124 obras), 2 review,
     6 reject**. Escritura **reversible** ejecutada: de las 124 aceptadas, **42 obras** tenían persona
     nuestra existente y se escribieron (`works_person_roles` rol 1) con historial en
     `work_attribution_history` (`operation=assign|replace|revert`); **82 aceptadas sin persona
     nuestra → revisión** (no se crean personas). Circuito verificado: apply → auditoría → revert →
     re-apply. Decisiones en `G:\\rism\\rism_decisions.csv`; escritor
     `scripts/apply_rism_attributions.py` (dry-run por defecto).
   - **BATCH2 (2026-09-19)**: enlace `RISM person → persons` por identificador (GND/VIAF) medido en
     `docsNew/rism-enlace-82.md`: de las 82 aceptadas sin persona, **52 enlazadas por VIAF**, 1 por
     nombre, 1 ambigua, 28 sin identidad. **Aplicadas 29** (solo VIAF, excluido Haydn): Byrd 20,
     Foster 2, Matos 2, Beethoven 2, Lasso 1, Schubert 1, Dowland 1. Historial `assign`: 29; Haydn
     `assign`=0. Total RISM vivo: **71 obras** (42 + 29).
   - **Pendiente de limpieza de datos**: la persona `f1f53fb0…` (Haydn) está **mal fusionada**
     (nombre de Michael, 26 alias y VIAF de Joseph) → decidir renombrar a Joseph o separar Michael
     antes de aplicar sus 23 obras. Y hay **174 personas con nombre `Arranged from …`/`from …`**
     (incluida `Arranged from Stephen Foster`, que recibió 2 asignaciones) → limpieza/merge a revisar.
   - **Corrección Haydn aplicada (2026-09-19)**: `scripts/correct_haydn_person.py` (dry-run →
     apply). `f1f53fb0…` → **`Joseph Haydn`** (given/family/sort + 1732/1809, `reviewed`, motivo del
     import); **3 alias de Michael movidos** a `96714c71…` (Michael Haydn); identidades (VIAF/QID/
     MBID/ISNI) conservadas; roles intactos (476/2/313); 1 sola persona «Joseph Haydn». Historial en
     `persons_correction_history` (before/after JSON, `operation=correct|revert`). Después, las
     **23 asignaciones Haydn** con `operation='assign'` → BATCH2 = **52**, total RISM vivo = **94**
     (42 + 52). Pendiente: las 174 `from/Arranged from`, 28 `sin_identidad`, 1 ambigua, 1 nombre,
     394 `inferred`.
10. **`works_person_import`** (386.004 filas, 56.426 nombres distintos): contra `persons` **34.042
    (60 %)**, sin match **21.745 (38,5 %)**, solo en RISM **627**, ambiguos en RISM 480. RISM aporta
    poco aquí; el grueso sin match no está en RISM (ruido de import, p. ej. "Set of QuadrillesNo3").
11. **Calidad de nombres en `persons`** (2026-09-20, en curso). Reapertura de `persons` por los
    nombres importados del texto de obra (PDMX): **988 filas sospechosas** de 45.217. Diagnóstico en
    `docsNew/diagnostico-persons-limpieza.md`.
    - **Fase 1 aplicada y verificada**: **216** ocultadas (`persons_visible = 0`) + **10**
      renombradas (prefijo `:`/`'`/`?` y fechas `(18501922)`→`(1850-1922)`), con
      `persons_correction_history` y ciclo revert/re-apply. Visibles 44.740 → **44.524**.
      Script `scripts/cleanup_persons_phase1.py` (`--apply` / `--revert <batch>`).
    - Casos de la captura del usuario identificados: estaban en **inglés** (`'No 12'` = «¿Número 12?»,
      `!! Go to stettings` = «¡¡Vaya a la configuración!!», `?Raisin Band?` = «¿Banda de pasas?»).
    - **Criterio fijado**: banda/ensemble **con nombre** = **artista** → se queda en `persons`
      (roles 1/10). `ensembles` es catálogo de **tipos** vocales (`ensembles_code` UNIQUE +
      `ensemble_voices`), no de agrupaciones con nombre.
    - **Codificación**: `utf8mb4` correcto; las **244** filas mojibake no se recuperan
      reinterpretando la cadena (3/244) → hay que releer el nombre de la fuente.
    - **Pendiente**: placeholders (4 filas, 2.015 obras) → `works.works_attr_type`
      (`TRADICIONAL`/`ATRIBUIDA`) + `works_attribution_note`, sin crear persona; fase 2 (dividir
      pares pegados y bloques de crédito, 10 diferidos); mojibake (244).
12. **`GET /api/v1/persons?role=…`** (pedido 2026-09-20): sustituye a la antigua API de composer.
    Multivalor (`composer,arranger`) y roles `composer`, `arranger`, `performer`, `editor`; con la
    regla de que **`composer` devuelve solo personas con ≥1 obra**. Pendiente de implementar.


---

## 8. Fusión de identidad (2026-09-17)

Se unificaron `persons_authority` + `persons_authority_name` + `persons_identifiers` en una
sola tabla **`persons_identity`** (EAV con `persons_id` opcional):

- `persons_id IS NULL` = **candidato** (persona externa aún no incorporada).
- Fila **canónica** por persona/candidato: `identity_is_anchor = 1`, `identity_type = ''`.
- `identity_type` + `identity_value` = identificador (wikidata_qid, viaf, imslp, isni, gnd,
  discogs, musicbrainz, cluster…), con `identity_source` (authority|wikidata|maestro|cpdl|web).
- Los nombres de autoridad con persona pasaron a **`persons_aliases`**.
- **Verdad de nombres**: `persons.persons_name` (canónico) + `persons_aliases` (variantes).

Estado tras la fusión:
| | |
|---|---|
| `persons` | 47.157 |
| `persons_identity` | 124.206 (canónicas 47.157 = 1 por persona; candidatos 59.619; ids 62.124) |
| `persons_aliases` | 44.723 |

Consultas de resolución:
- **nombre → persona/id**: `SELECT persons_id, identity_value FROM persons_identity WHERE identity_name_norm = ?`
- **persona → ids**: `SELECT identity_type, identity_value FROM persons_identity WHERE persons_id = ?`

Script: `scripts/migrate_identity_fusion.sql`. Backups: `persons_authority_bak`,
`persons_authority_name_bak`, `persons_identifiers_bak`.

**Resuelto (2026-09-17)**: los scripts de reconstrucción están repuntados a
`persons_identity`/`persons_evidence` y verificados en seco: `resolve_persons.py`,
`link_works_person_import.py`, `incorporate_from_authority.py`,
`incorporate_cpdl_composers.py`, `resolve_composers_web.py` y `resolve_import_ai.py`.
`normalize_authority_names.py` quedó obsoleto (lo sustituye `normalize_identity_names.py`).

Se **retiraron 8 scripts** del pipeline antiguo que apuntaban a tablas ya inexistentes
(`composer_candidate`, `composer_identity_resolution`, `composer_authority`,
`composer_identifiers`, `composer_evidence`, `persons_authority*`, `persons_identifiers`):
`candidate_cleanup.py`, `candidate_priority.py`, `catalog_statistics.py`,
`incorporate_candidates.py`, `incorporate_resolutions.py`, `load_composer_authority.py`,
`test_authority_coverage.py`, `normalize_authority_names.py`.

Con esto el **módulo de identidad queda cerrado** (código). En datos siguen pendientes los
547 artistas de staging y las obras sin compositor (ver §9 para cifras actuales).

---

## 9. Contratos de repositorios contra el esquema nuevo (2026-09-17)

Los tests unitarios usan **fakes en memoria** y no ejecutan SQL; sólo `tests/integration`
tocaba la BBDD, con 8 comprobaciones de existencia. Se ha añadido
**`tests/integration/test_repository_contracts.py`** (17 tests) que ejercitan cada
repositorio contra el esquema nuevo, en una **copia** `osap-storage_test` (nunca la
principal, porque algunas pruebas escriben y limpian):

| Repositorio | Qué valida |
|---|---|
| `SqlWorkRepository` | round-trip por `works_key`; listas desde `work_genres`/`work_instruments`; `replace_*` con restauración; `list_by_composer` = rol 1; búsqueda |
| `SqlComposerRepository` | `list_summaries` solo con obras; `get_detail` con identificadores/alias desde `persons_identity`/`persons_aliases`; alta de alias + `resolve_by_normalized`; `find_by_identifier`; alta de identificador y de evidencia (con limpieza) |
| `SqlVotingRepository` | `add_vote` → `recompute_all` → `work_statistics` |
| `SqlCatalogueRepository` | `list_all` / `get_by_prefix` |
| `SqlTableCrudRepository` | whitelist completa (incl. tablas CPDL nuevas); FK nuevas; columnas nuevas; `read_one` |

Ejecución:

    $env:OSAP_TEST_DB = "1"; $env:OSAP_TEST_DB_NAME = "osap-storage_test"
    .venv\\Scripts\\python.exe -m pytest tests/integration -q    # 25 pasan

**Bugs reales encontrados y corregidos**:
- `SqlComposerRepository.add_identifier` y `set_musicbrainz_id` insertaban en
  `persons_identity` **sin `identity_name`/`identity_name_norm`** (NOT NULL). En modo no
  estricto entraba `''` con warning; con `STRICT_TRANS_TABLES` fallaría.
- La whitelist del CRUD genérico no incluía `cpdl_editions`, `cpdl_edition_files` ni
  `cpdl_edition_persons`.

**Cifras actuales de atribución** (rol 1 en `works_person_roles`):
`works` 310.455 · con compositor **133.431** · sin compositor **177.024** (174.060 PDMX +
2.964 CPDL) · `persons` 45.217 · relaciones rol 1 **134.374** · personas sin obra **1.891**.
De las PDMX sin compositor, **162.974 no tienen ni fila en `works_person_import`** (el dato
no está en la BBDD; habría que leerlo de los `.mxl`), por lo que la atribución depende del
**fichero de compositores** (decisión pendiente #1).

### 9.1 Renombrado `Composer` → `Person` (2026-09-17, en curso)

Decisión #3 resuelta con **alcance por pasos y alias de compatibilidad** (elegido): se
renombra la capa canónica y se mantienen los nombres antiguos para no romper nada.

Hecho:
- `domain/entities/person.py` — `Person`, `PersonAlias`, `PersonIdentifier`, `PersonEvidence`,
  `PersonCreationEvidence`, `PersonSummary`, `PersonDetail`, `PersonWorkRef`, `PersonStatus`,
  `PersonResolution`, `PersonResolutionDecision`, `MergePersonsResult`, `UNKNOWN_PERSON(_ID)`.
- `domain/ports/person_repository.py` — `PersonRepository`.
- `infrastructure/repositories/sql_person_repository.py` — `SqlPersonRepository` (implementación canónica).
- Compatibilidad (re-export): `domain/entities/composer.py`, `domain/ports/composer_repository.py`,
  `infrastructure/repositories/sql_composer_repository.py`.
- Migrados a los nombres nuevos: `infrastructure/container.py`, `scripts/run_works_matching.py`
  y los tests de integración.

Campos renombrados (**`composer_id` → `person_id`**, incluidos `composer_ids`,
`from_/target_/old_/candidate_composer_id` y el camelCase `composerId`/`composerIds` de la web)
en **ambos repos**, propagado a `application/use_cases/*`, `api/*` (schemas/rutas/DTOs),
`scripts/*` y tests; también el contrato consumido por `osap-api`
(`storage/work_store.py`, `storage/storage_composer_client.py`, `api/contracts/votes.py`, web).

Verificación:
- `osap-storage`: `ruff` limpio · **231 unit + 31 integración en verde** (el contrato de la API
  ya expone `person_id`).
- `osap-api`: **654 tests pasan**; 2 fallos **ajenos al renombrado** (falta
  `openapi_spec_validator` porque se ejecutó con el venv de osap-storage —el suyo apunta a
  `C:\Python313`, inexistente— y `test_select_best_representation` por `imslp: descarga
  fallida`). Su venv hay que recrearlo para correr la suite en condiciones.

Pendiente (paso posterior): **nombres de método** del puerto (`rename_composer`,
`update_composer`, `prune_zero_work_composers`…), del módulo `composer_admin`, las **rutas**
`/api/admin/composers*` y `/api/v1/composers*`, y los nombres de módulo `composer_*`. No
afectan al contrato de datos ya renombrado.

---

## 10. Publicación de la API: validación end-to-end (2026-09-18)

Objetivo: comprobar que la app arranca y responde **contra la BBDD nueva** (no contra fakes),
que es el requisito para publicar. API levantada con el venv real sobre `osap-storage`
(`config.yaml`) en `127.0.0.1:8000`.

**Smoke test completo (sin fallos)**
- **34/34** endpoints GET: provider (`/api/version`, `/api/lookup`, `/api/search`,
  `/api/resource/{id}`), `/api/v1/*` (works, composers, catalogues, cpdl, files, providers,
  archives, statistics), admin (composers, works, tables, epochs).
- **10/10** rutas HTML/web: `/`, `/about`, `/works`, `/works/{id}`, `/search`, `/statistics`,
  `/admin`, `/admin/obras`, `/admin/maestros`, `/api`.
- **7/7** desplegables de relaciones de la obra (`persons`, `roles`, `genres`, `instruments`,
  `languages`, `voices`, `ensembles`).
- Frontend: `tsc --noEmit` limpio y `vite build` correcto (mismos hashes de assets).

**Bugs reales encontrados y corregidos** (los tests unitarios no los veían porque usan fakes):

1. **`files` devolvía 500** — `FileRead.sha256: str` no admitía `NULL`, y `files.sha256` está a
   `NULL` en las **254.035** filas (pendiente §7 #2). Afectaba a `/api/v1/files` y
   `/api/v1/files/{id}`. Corregido en `api/schemas.py` (`str | None`) y
   `domain/entities/file.py` (`sha256: str | None`, `storage_key()` con error explícito si
   falta); `VerifyItem.expected_sha256` también pasa a opcional.
2. **`/api/admin/works` devolvía 500** — `_to_detail` pasaba el DTO del caso de uso
   (que envuelve `.work`) a `WorkAdminDetail.model_validate`, que espera los campos planos.
   Corregido aplanando explícitamente el `Work` + listas en `api/routes/admin_works.py`.

**Tests de regresión** (`tests/integration/test_api_contracts.py`, +3):

    $env:OSAP_TEST_DB = "1"; $env:OSAP_TEST_DB_NAME = "osap-storage_test"
    .venv\\Scripts\\python.exe -m pytest -q    # 265 pasan (unit + integración juntos)

- `test_files_endpoint_tolerates_null_sha256`
- `test_admin_works_endpoints_read_new_schema`
- `test_work_relations_add_and_remove` (alta/baja reversible de un género)

**Aislamiento de tests corregido**: `test_admin_composers`, `test_provider_contract` y
`test_voting` fijaban `OSAP_CONFIG` con `os.environ[...] =` (sin restaurar), así que al correr
unit + integración en la misma sesión heredaban una config temporal (`db_user: dev`) y toda la
integración fallaba con *Access denied*. Ahora usan `monkeypatch.setenv` (también
`test_admin_visibility`, que importa el helper). La suite completa corre en un solo comando.

**Observaciones menores** (no bloquean publicar):
- El desplegable de personas sirve ~44.7k opciones sin paginación ni búsqueda en servidor;
  conviene un selector con búsqueda cuando se retome la Fase 7.
- Los endpoints de escritura se validan en la copia `osap-storage_test`; no se mutó la BBDD
  principal durante el smoke test.
