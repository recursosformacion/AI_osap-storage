# Cierre Fase 5-6 — CLI/scripts y migraciones (2026-09-19)

## Fase 5 — CLI y scripts
- **`infrastructure/cli.py`**: importa y sus **23 atributos de `Container` existen** (0 faltantes).
  Comandos presentes: `register-works`, `enrich-metadata`, `populate-composers`,
  `musicbrainz-enrich`, `recompute-statistics`. **Sin `sync-authority`/`candidate`/`resolution`**
  (flujos abandonados ya retirados en Fase 1).
- **Scripts**: **0 referencias** a `osap-storage_new` (ya actualizados).
- **Retirados (flujo abandonado de resolución de compositores; reversibles vía git)**:
  - `scripts/composer_review_ai.py`
  - `scripts/incorporate_cpdl_composers.py`
  - `scripts/incorporate_from_authority.py`
  - `scripts/resolve_composers_web.py` (único que importaba el anterior)
  - `scripts/verify_omr_representations.py`
  - Verificado que **ningún** otro script los importa.

## Fase 6 — Migraciones y arranque
- **Esquema viejo archivado**: `infrastructure/db/migrations_v1/` (**40** ficheros 001–041; no deben
  aplicarse).
- **Baseline del fork**: `infrastructure/db/migrations/001_baseline_schema.sql` + `README.md`.
- **Runner**: `infrastructure/db/migrate.py` aplica los `.sql` en orden alfabético y registra en
  `schema_migrations` (**1 fila**: el baseline aplicado).
- **Bootstrap/salud**: provider por defecto y `/api/v1/health` operativos (validado en Fase 4).

## Verificación
- `ruff` limpio · **294 tests** en verde (unit + integración).

## Cierre
Fase 5-6 **cerrada**: CLI alineado, scripts de flujos muertos retirados, migraciones con baseline y
runner funcionando. Sin pendientes estructurales.
