# Auditoría de código — aplicación `osap-storage`

- **Repositorio:** `D:\Proyectos\AI_OSAP\osap-storage`
- **Tipo:** API FastAPI + CLI, Python 3.12 (target `py311`), arquitectura limpia (capas `api → application → domain`, con `infrastructure` apuntando a `domain`).
- **Base de datos:** MariaDB 10.4.32 (ver `docs/auditoria-bd-osap-storage.md`).
- **Metodología:** revisión estática del árbol de código (`domain/`, `application/`, `infrastructure/`, `api/`, `scripts/`) cruzada con migraciones SQL (`infrastructure/db/migrations/`) y documentación (`docs/*.md`). No se modificó código ni se ejecutaron writes. Se comparó el esquema vivo (extracción `information_schema`) con el código y con las migraciones. Los resultados de `ruff` y `mypy` se indican al final.

---

## 1. Resumen de hallazgos (índice)

| # | Gravedad | Área | Resumen |
|---|---|---|---|
| 1 | Crítica | Configuración/Arranque | La validación de configuración de producción está deshabilitada (dependencia faltante). |
| 2 | Crítica | API/Administración | `/api/admin/tables` (CRUD genérico) con whitelist desactualizada y sin protección de invariantes. |
| 3 | Crítica | Migraciones/Esquema | `works.genre_id` es un cambio *out-of-band* (no está en migraciones ni en código). |
| 4 | Alta | Esquema/Esquema-código | `archive_entries.work_id` carece de FK e índice en la BD viva, pese a la migración. |
| 5 | Alta | Esquema/Esquema-código | `composer_statistics` se crea en migraciones pero falta en la BD viva. |
| 6 | Alta | Refactorización | Refactorización a vocabularios normalizados (migraciones 038–041) a medio hacer: tablas muertas. |
| 7 | Alta | Arquitectura/DIP | `application` importa clientes HTTP concretos de `infrastructure` en lugar de *ports*. |
| 8 | Media-Alta | Seguridad | CRUD genérico permite borrados en cascada y escritura de campos inmutables sin auditoría. |
| 9 | Media | Authn | `EXEMPT_PATHS` solo excluye rutas exactas → posible 401 en sub-páginas del shell admin. |
| 10 | Media | Migraciones | `migrate.py` no es atómico por migración y el splitter SQL es frágil. |
| 11 | Media | Calidad | Fechas/años extraídos del título con regex → falsos positivos; caché MB sin TTL. |
| 12 | Media-Baja | Deuda | `ruff` pasa; `mypy` está configurado demasiado laxo y no detecta errores de tipo. |

---

## 2. Hallazgos detallados

### Hallazgo 1 — Validación de configuración deshabilitada en arranque (Crítica)

**Ubicación:** `api/main.py:44-55` (`_validate_config`) y `infrastructure/cli.py:623-632`.

```python
def _validate_config() -> None:
    try:
        from osap.bootstrap.configuration import validate_generic_service_config
    except ImportError:
        return                 # <-- en este repo la import falla siempre
    ...
    validate_generic_service_config("osap-storage", data, config_path)
```

**Descripción:** `osap.bootstrap.configuration` **no está declarado como dependencia** en `pyproject.toml` ni instalado en el entorno. Por tanto `import osap.bootstrap.configuration` falla con `ModuleNotFoundError: No module named 'osap'` (verificado). En `main.py` la `except ImportError: return` **silencia el error y omite por completo la validación**; en `cli.py` existe una guardia que evita el `TypeError` pero alivia de la misma forma. Como consecuencia, ni la API ni el CLI validan `db.host/user/password/name`, `http.host/port`, `public_base_url`, la configuración del proveedor local, ni la URL/JWKS de autenticación.

**Impacto:** En producción la aplicación puede arrancar y servir tráfico con configuración errónea o incompleta (credenciales de BD malas, `public_base_url` incorrecto, auth deshabilitada o apuntando al issuer equivocado) sin que nada lo detecte en arranque. El comentario de `EXEMPT_PATHS`/auth sugiere que la config `auth_enabled` controla el auth; validar la config es el Único mecanismo de "no arranques si la config no cuadra".

**Recomendación:** Declarar la dependencia `osap` (o version del *bootstrap* de OSAP) en `pyproject.toml`; si es opcional, **no silenciar** el `ImportError` en `main.py` — fallar en startup (`raise SystemExit(...)`) hasta que la config sea validable. Reusar la misma función en `cli.py` en vez de duplicar el patrón. No confiar nunca en que "la import fallida" significa "todo correcto".

---

### Hallazgo 2 — CRUD genérico `/api/admin/tables` desactualizado y sin salvaguardas de dominio (Crítica)

**Ubicación:** `application/use_cases/table_crud.py`, `infrastructure/repositories/sql_table_crud_repository.py:9-36` (`TABLES`), `api/routes/admin_tables.py`.

**Descripción:**
- El `whitelist TABLES` incluye **`composer_creation_evidence`**, tabla que **no existe en la BD** (se llama `composer_evidence`). Cualquier `GET /api/admin/tables/composer_creation_evidence` ejecuta `SELECT * FROM composer_creation_evidence` → **500**. El admin que liste/edita confusión.
- El whitelist **omite 16 tablas reales** de la BD: `authority_identifiers`, `authority_sync_state`, `composer_authority`, `composer_authority_names`, `composer_candidate`, `composer_identity_resolution`, `composer_resolution`, `cpdl_pages`, `cpdl_voicings`, `epochs`, `genres`, `genre_mappings`, `instruments`, `instrument_categories`, `schema_migrations`, `works_instruments`. Estas no son administrables/visibles por la API genérica.
- El CRUD es **ciego a invariantes de dominio**: `create` no filtra que se inserte `id`/`created_at`/`updated_at` (se aceptan si vienen en el `payload`); `update` no protege campos críticos (`composers.status`, `composers.merged_into`, `votes.vote_day`, `files.sha256`, `storage_providers.name`, etc.).
- Las borrados usan `ON DELETE CASCADE` reales en la BD: `DELETE /admin/tables/composers/{id}` borraría en cascarola `composer_aliases`, `composer_biographies`, `composer_evidence`, `composer_identifiers`, `composer_merge_history` (origen) y `works`→... dependiendo del cascade. **No hay confirmación ni auditoría de la acción.**
- La ruta usa `table` como *path parameter* y `pk_value: Any`; el repo mitiga la inyección de nombre de tabla con el whitelist y valida columnas contra `information_schema` (`_valid_columns`), pero **el `whitelist` está desincronizado**, de modo que la protección de "tabla permitida" es inútil precisamente para las tablas peligrosas.

**Impacto:** exposición de una API de "admin de base de datos" sobre tablas sensibles (compositores, identificaciones, votos) sin control de integridad ni trazabilidad operacional. El drift del whitelist prueba el riesgo: la capa de autorización (scope `storage:admin`) filtra quién llama, pero dentro de ella no hay defensa contra borrados destruidos.

**Recomendación:** Sincronizar `TABLES` con el esquema real (o generar el whitelist a partir de `information_schema` con una lista de exclusión explícita). Añadir una capa de *allow-list de columnas escribibles* por tabla (excluir PK, timestamps, campos de dominio críticos). Requerir confirmación y registrar borrados/modificaciones en una tabla de auditoría. Considerar si realmente se necesita CRUD genérico sobre tablas de identidad/votos.

---

### Hallazgo 3 — `works.genre_id` es un cambio de esquema *out-of-band* (Crítica-esquema)

**Ubicación:** tabla `works`, columna `genre_id` con FK `fk_works_genre_genres → genres(id)` (ver auditoría BD §3.10).

**Descripción:** La columna y su FK existen en la BD viva, pero **ninguna migración del repositorio (001–041) la crea** y el **código Python nunca la escribe ni lee** (`SqlWorkRepository.create/update` no incluyen `genre_id`; el `grep` de `genre_id` en `*.py` devuelve 0). Si la BD se reconstruye desde migraciones, la columna desaparece. Es el reflejo de la refactorización de normalización de géneros (migración 040) que se anunció pero no se completó en código.

**Impacto:** inconsistencia entre "qué crea la migración" y "qué hay en prod"; riesgo de pérdida de datos al rebuild; columna huérfano que despista (un lector verá `genre_id` y `genre` texto coexistiendo sin sincronizar).

**Recomendación:** Si se quiere normalizar, añadir una **migración `042_add_works_genre_id.sql`** que la cree, y escribir/leer `genre_id` en `SqlWorkRepository` y en el pipeline de enriquecimiento; de lo contrario revertir la columna y la FK del entorno prod.

---

### Hallazgo 4 — `archive_entries.work_id` sin FK ni índice en la BD viva (Alta)

**Ubicación:** `infrastructure/db/migrations/007_works.sql:21-27`.

**Descripción:** La migración añade `work_id` a `archive_entries`, crea el índice `idx_archive_entries_work` y la FK `fk_archive_entries_work`. En la **BD viva` (comprobado con `SHOW INDEX` y `information_schema.KEY_COLUMN_USAGE`) la columna existe pero **carece de índice y de FK**. Con 251 589 filas, cualquier `JOIN works↔archive_entries` por `work_id` implica un escaneo completo de tabla, y no hay integridad referencial (pueden quedar referencias a obras borradas).

**Impacto:** rendimiento degradado en listados/resoluciones de entradas por obra, y posible inconsistencia (entry apuntando a obra inexistente).

**Recomendación:** Re-aplicar la migración que crea el índice y la FK (o investigar por qué se eliminaron; posiblemente se hicieron `SET foreign_key_checks=0` durante un backfill y se olvidó recrear). Añadir una migración idempotente que asegure `idx_archive_entries_work` + `fk_archive_entries_work`.

---

### Hallazgo 5 — `composer_statistics`: tabla creada por migración pero ausente en la BD viva (Alta)

**Ubicación:** `infrastructure/db/migrations/012_voting_statistics.sql:35-43` (`CREATE TABLE composer_statistics`) y `013_voting_statistics_v1.sql:13-19` (`ALTER TABLE composer_statistics`).

**Descripción:** Las migraciones 012/013 crean y reestructuran `composer_statistics`, pero **la tabla no existe en la BD viva** (ver lista de tablas: ausente). El código (`sql_voting_repository.py:107` y `:159`) comenta que `composer_statistics` está "retirado" y calcula las estadísticas de compositor en vivo con un `SELECT` agregado. Por tanto la BD de prod fue modificada manualmente (se hizo `DROP TABLE composer_statistics`) y **esa eliminación no quedó registrada en ninguna migración**. La migración 013 queda inconsistente con el estado real, y cualquier rebuild desde el esquema recrearía `composer_statistics` y aplicaría 013, pero prod no la tendría → prod diverge de migrations.

**Impacto:** desalineación entre código/migraciones y BD; si se vuelve a aplicar la migración sobre prod, `ALTER TABLE composer_statistics` fallaría (no existe) o la recrearía de forma inesperada.

**Recomendación:** Añadir una migración que borre explícitamente `composer_statistics` (o migre su contenido) y documente el "retiro", en lugar de dejar el DROP fuera de control de versiones.

---

### Hallazgo 6 — Refactorización a vocabularios normalizados a medio hacer (Alta)

**Ubicación:** migraciones `038_epochs.sql`, `039_normalize_biography_era.sql`, `040_genres.sql`, `041_instrument_catalog.sql`; código `infrastructure/repositories/sql_work_repository.py` y `application/use_cases/work_admin.py` / `admin_works.py`.

**Descripción:** Las migraciones 038–041 introducen vocabularios normalizados (épocas, géneros macro, instrumentos/categorías, asignación normalizada `works_instruments`, `works.genre_id`). Sin embargo, **la capa de aplicación casi no los consume**:
- Sólo `api/routes/admin_epochs.py` lee `epochs` (listado admin).
- `genres`, `genre_mappings`, `instruments`, `instrument_categories`, `works_instruments` **tienen 0 referencias SQL en el código** (verificado: `FROM instruments`, `INSERT INTO genres`, `FROM genre_mappings`, `INSERT INTO works_instruments`, … ausentes).
- La aplicación persiste género/instrumentos como **texto libre** en `works.genre`, `work_genres.genre`, `work_instruments.instrument`, `works.instrumentation`, `works.tags`; **nunca escribe** `works.genre_id` ni la tabla normalizada `works_instruments`.
- `composer_biographies.biography_era` sigue siendo texto libre aunque la migración 039 comenta que "se mapeará a `epoch_id` FK".
- El whitelist de `table_crud` ni siquiera incluye `works_instruments`, aunque físicamente exista, reflejando que el equipo no ha decidido cómo exponer/escribir la normalizada.

**Impacto:** dos fuentes de verdad para género e instrumentos (texto vs catálogo normalizado); migraciones "preparando" normalización que el código no aplica → esfuerzo de refactorización incompleto y posible duplicación/conflicto de datos cuando se active.

**Recomendación:** Decidir el plan de migración de `work_genres`/`work_instruments` → `genres`/`works_instruments` y ejecutarlo, o revertir las tablas normalizadas no usadas. No mantener dos mecanismos de asignación activos sin sincronizarlos.

---

### Hallazgo 7 — Violación de DIP / arquitectura de capas (Alta)

**Ubicación:**
- `application/services/composer_recovery.py:17` → `from infrastructure.services.osap_api_client import OsapApiClient`
- `application/use_cases/authority_sync.py:15` → `from infrastructure.services.metabrainz_client import MetabrainzClient`
- `application/use_cases/musicbrainz_enrich.py:7` → `from infrastructure.services.musicbrainz_client import MusicBrainzClient`

**Descripción:** La capa `application` (reglas de negocio) importa **clientes HTTP concretos** de infraestructura en lugar de *ports*. La arquitectura declarada (`domain.ports.*`) sí define puertos como `MusicBrainzCacheRepository` (usado por `CachedMusicBrainzClient`), pero el cliente MB en sí y `osap_api_client`/`metabrainz_client` son clases concretas inyectadas directamente. La capa de dominio está limpia (0 imports de `infrastructure`/`application`), pero `application` no respeta el hexágono.

**Impacto:** acoplamiento a implementaciones HTTP concretas (hard test, hard mock); una sola entidad (`ComposerRecoveryService`) depende de `OsapApiClient` importado dentro del módulo, imposibilitando sustituirlo (p.ej. un cliente en memoria en tests sin parche).

**Recomendación:** Definir *ports* (`ComposerResolverPort`/`OsapApiPort`, `MusicBrainzPort`) en `domain.ports`, inyectar implementaciones por el contenedor (`infrastructure/container.py`), y aislar las respuestas del cliente HTTP en adaptadores.

---

### Hallazgo 8 — CRUD genérico sin auditoría y con borrados en cascada (Media-Alta)

**Ubicación:** `api/routes/admin_tables.py:96-113` (`delete_row`), `infrastructure/repositories/sql_table_crud_repository.py:113-119`.

**Descripción:** `DELETE FROM {table} WHERE {pk}=?` sobre tablas como `composers` dispara `ON DELETE CASCADE` sobre `composer_aliases`, `composer_biographies`, `composer_evidence`, `composer_identifiers`, `composer_merge_history` y (`works`? `works.composer_id` no es FK, pero `votes.work_id` sí cascadea, `work_statistics` sí). No hay confirmación client-side que impida el borrado, ni tabla de bitácora que registre quién/borrró qué ni cuándo (más allá del `cur.rowcount`).

**Recomendación:** Registrar borrados/exUpdates en una tabla `audit_log`; rechazar borrados directos de entidades con FKs sensibles (p.ej. `composers`) y ofrecer solo el flujo de *merge* (ya existe `merge_composers`). Añadir `created_by`/`updated_by`/`deleted_by` cuando se exponga edición.

---

### Hallazgo 9 — `EXEMPT_PATHS` excluye rutas exactas, no prefijos (Media)

**Ubicación:** `api/security.py:22-23` y `:172-181`.

**Descripción:** `EXEMPT_PATHS = {"/api/v1/health", "/metrics", "/admin", "/admin/maestros", "/admin/obras"}` y `dispatch` exige `path in EXEMPT_PATHS`. Las **sub-rutas** (`/admin/maestros/x`, `/admin/obras/y`) no están exentas → exigen Bearer. Como el shell HTML (`/admin/*`) no envía token de servicio, navegar dentro del admin devolvería 401, a menos que las páginas sirvan desde rutas distintas. La lista mixta de `/admin` (público) y `/api/admin/*` (requiere `storage:admin`) indica un diseño de exención frágil.

**Recomendación:** Eximir por prefijo (`/admin`, `/api/v1/health`, `/metrics`) de forma coherente, y separar el shell (HTML, público o con auth de usuario) del API admin (service token). Revisar rutas reales de `pages`/`admin_*` para confirmar.

---

### Hallazgo 10 — `migrate.py`: migraciones no atómicas y splitter SQL frágil (Media)

**Ubicación:** `infrastructure/db/migrate.py:32-40` (bucle) y `:43-66` (`_split_statements`).

**Descripción:**
- Cada fichero se aplica sentencia a sentencia **fuera de transacción explícita**: si un `ALTER` intermedio falla, la migración parcial ya está aplicada pero **no se registra en `schema_migrations`** (el `INSERT` va al final). El siguiente arranque reejecutará el fichero completo → error distinto ("already exists"), bloqueando el arranque. No hay rollback por archivo.
- `_split_statements` divide por `;` línea a línea sin parsear literales ni comentarios. No maneja `#` ni bloques `/* */`, ni `;` dentro de strings ni comentarios *inline* (`code;  -- x` produciría una "sentencia" `-- x` que falla). Hoy no hay `;` dentro de strings (verificado), pero cualquier seed futuro con `;` en un texto rompería la migración.

**Recomendación:** Envolver cada migración en `START TRANSACTION ... COMMIT` (y `ROLLBACK` en error). Usar `sqlparse` (o al menos dividir respetando strings/comentarios) para tokenizar. O bien usar `-- +goose Up / +goose Down` y un runner de migrations probado.

---

### Hallazgo 11 — Extracción de año/URL con regex heurístico y caché sin TTL (Media)

**Ubicación:** `application/services/composer_recovery.py:195-199` (`extract_year`) y `infrastructure/services/musicbrainz_client.py:62-81` + `infrastructure/repositories/sql_musicbrainz_cache_repository.py:20-25`.

**Descripción:**
- `extract_year` aplica `\b(1[89]\d\d|20\d\d)\b` sobre `work.title`. Un título como `"Suite Op. 1014 de 1812"` o `"1812 / Overture"` devolvería cualquier número de 4 cifras entre 1800 y 2099 que aparezca (incluidos números de catálogo u años de edición), enviando un `year` erróneo a `osap-api`. La obra ya almacena `works.year` y `works.catalogue`; usarlos sería más preciso.
- La caché de MusicBrainz `INSERT … ON DUPLICATE KEY UPDATE payload=VALUES(payload)` **no actualiza `created_at`** y **no hay expiración ni evictación**: la cache crece indefinidamente y sirve respuestas potencialmente obsoletas de MB para siempre. MB evoluciona (correcciones de identidad) y la caché nunca las refleja.

**Recomendación:** Derivar el año de `works.year`/`works.catalogue`; añadir columna `expires_at` a la caché y una rutina de limpieza (o TTL en el cliente con `updated_at`).

---

### Hallazgo 12 — `ruff` sí, pero `mypy` está demasiado relajado (Media-Baja)

**Ubicación:** `pyproject.toml:[tool.mypy]` y `[tool.ruff.lint]`.

**Descripción:** `ruff` (E, F, I, UP, B, SIM) pasa sin errores. `mypy` está configurado con `disallow_untyped_defs=false`, `check_untyped_defs=false`, `no_implicit_optional=false`, `warn_unused_ignores=false` y `disable_error_code=["arg-type"]`. El comentario del propio `pyproject.toml` (líneas 65–68) reconoce la deuda: "Desactivamos arg-type (deuda sistémica de diseño), manteniendo el resto". En la práctica **mypy no detecta errores de tipo**; el `# type: ignore[call-arg]` en `Settings()` (`api/main.py:61` y `:139`) encubre que `Settings` requiere argumentos (se construye con state global) → oculta bugs de wiring en arranque.

**Recomendación:** Activar `check_untyped_defs=true` y `warn_unused_ignores=true` gradualmente; reemplazar los `# type: ignore[call-arg]` en `Settings()` por una factory que reciba explícitamente `env`/paths; migrar `disable_error_code=["arg-type"]` a un `# type: ignore` punto por punto. Considerar `pyright` como reforzamiento (especialmente para los `dict` dinámicos del CRUD).

---

## 3. Observaciones menores / deuda técnica (sin afilar)

- `SqlWorkRepository.update` (`infrastructure/repositories/sql_work_repository.py:60-98`) **no persiste** `genre_id`, `music_digest`, `work_key` ni `subtitle`... incluye `subtitle` (línea 76). `music_digest` está destinado a rellenarse offline (`scripts/analyze_works_content.py`); `genre_id` está fuera de código. Está dentro de lo esperado, pero conviene documentarlo.
- `SqlWorkRepository._replace`/`_get_list`/`get_lists_bulk` interpolan `{table}`/`{column}` con f-strings (`infrastructure/repositories/sql_work_repository.py:163,170,189,219`). Seguros porque los valores son constantes internas, pero **mezclan la tabla legacy `work_instruments` con la normalizada `works_instruments`** (que no se usa) → fuente de confusión; refactorizar a un método tipado o borrar la rama `works_instruments` si no se usa.
- `Database.transaction` (`infrastructure/db/connection.py:46-63`) rollbacka en `except Exception` y hace `raise`, pero **no re-raise explícito de `conn.begin()` fallida**; y `close()` no cancela sesiones en vuelo. Menor.
- `cpdl_voicing.py` estaba referenciado por la migración y docs, pero **no existe en `infrastructure/services/`** (`File not found` al abrir el path sugerido); el código de CPDL puede estar incompleto/muerto (ver `cpdl_pages`/`cpdl_voicings` en la BD). Investigar.
- `RecordVote`/`GetWorkStatistics` validan existencia de la obra, pero `archive_entries.work_id` no tiene FK (Hallazgo 4) → no hay integridad referencial entre entry y obra.
- Posible **no-enforce de CHECK en MariaDB 10.4**: `votes.check` (`chk_votes_range CHECK (vote BETWEEN 1 AND 5)` definida en migración 012) — MariaDB 10.4 **parsea pero ignora** `CHECK` constraints (se hacen efectivos solo desde 10.6). La app valida en Python, pero no en BD. Evaluar `DROP`/reemplazar o subir versión. (No se verificó el `information_schema.CHECK_CONSTRAINTS`; aceptar como hipótesis.)

---

## 4. Matriz de capas (verificada)

| Capa | Importa de `infrastructure` | Importa de `application.api` |
|---|---|---|
| `domain/` | 0 (limpio) | 0 (limpio) |
| `application/` | **3 módulos importan clientes concretos** de infra (ver Hallazgo 7) | — |
| `infrastructure/` | — | importa `domain.*` (correcto) |
| `api/` | importa `infrastructure.*` (correcto, capa externa) | — |

---

## 5. Checklist de migraciones vs BD (divergencias detectadas)

| Migración | Define | BD viva | Estado |
|---|---|---|---|
| 007 | `archive_entries.work_id` + idx `idx_archive_entries_work` + FK `fk_archive_entries_work` | columna sí, **índice y FK no** | Divergencia ❌ |
| 007 | `works.genre_id`? | no | (no la define) |
| 038-041 | `epochs`, `genres`, `genre_mappings`, `instruments`, `instrument_categories`, `works_instruments`, `works.genre_id` (este último NO está en mig 040/041) | tablas sí; `genre_id` sí | `works.genre_id` out-of-band ❌ |
| 012-013 | `composer_statistics` (CREATE + ALTER) | **ausente** | Divergencia ❌ (DROP manual fuera de control) |
| 001-041 | 40 ficheros (no existe 024) | 40 aplicados registrados | Ok ✓ |

---

## 6. Conclusión

La base de código está bien estructurada (capa de dominio limpia, migraciones versionadas, `ruff` limpio) pero presenta **cuatro áreas de riesgo operativo/constructor**:

1. **Startup fragile:** la validación de config está deshabilitada → prod puede arrancar roto.
2. **Admin CRUD genérico:** whitelist roto y sin invariantas → riesgo de borrador/inconsistencia sobre tablas sensibles.
3. **Esquema vs código desincronizados:** `archive_entries.work_id`, `composer_statistics` y especialmente `works.genre_id` indican DBs mutadas manualmente o refactorizaciones incompletas.
4. **Refactorización de vocabulario a medias** (038–041) con tablas normalizadas sembradas pero no consumidas → dos fuentes de verdad.

Prioridad sugerida: (1) arreglar `_validate_config`/`osap` dependency; (2) sincronizar/restringir el CRUD admin; (3) reconciliar esquema prod con migraciones (índices, FK, `composer_statistics`, `genre_id`); (4) decidir y completar o revertir la normalización de géneros/instrumentos; (5) endurecer `mypy`.
