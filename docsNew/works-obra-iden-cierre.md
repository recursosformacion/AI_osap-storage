# Cierre `works_obra_iden` — legacy/no utilizada (2026-09-19)

## Búsqueda de referencias
- **Código Python**: **ninguna** referencia (`grep obra_iden` en `*.py` → 0, excluyendo `.venv`,
  worktrees y build).
- **SQL/migraciones**: solo `infrastructure/db/migrations/001_baseline_schema.sql` la define:
  - `works_obra_iden bigint(20) unsigned DEFAULT NULL COMMENT 'autoreferencia works.id'`
  - `KEY idx_works_obra_iden (works_obra_iden)`
  - `CONSTRAINT fk_works_obra_iden FOREIGN KEY (works_obra_iden) REFERENCES works(id) ON DELETE SET NULL`
- **Scripts / API / frontend**: sin referencias.
- **Documentación (ya decidido)**: `migracion-conversion.md` **decisión 6 — «se descarta usar
  `works_obra_iden`»**; `diseño-works-propuesta/revision` la dejan como autoreferencia sin reglas;
  notas de módulos `works` la marcan con 0 usos.

## Estado en la BBDD (`osap-storage`)
| | |
|---|---|
| Tipo | `bigint(20) unsigned NULL`, comentario "autoreferencia works.id" |
| Valores en 310.455 obras | **0 no nulos**, 0 distintos |
| Índice | `idx_works_obra_iden` (no único) |
| FK | `fk_works_obra_iden → works(id) ON DELETE SET NULL` (definida en la migración baseline) |

## Dependencias indirectas
- Sin usos funcionales: ninguna consulta, script, endpoint ni entidad la lee o escribe.
- Sin valores: no hay enlaces de autoreferencia que pudieran estar explotándose indirectamente.
- No hay otras tablas que dependan de ella.

## Decisión
> `works_obra_iden`: **sin usos en código ni datos funcionales → legacy/no utilizada → aspecto
> cerrado.** Se **conserva físicamente** (columna, índice y FK) por compatibilidad histórica; **no se
> elimina ahora**. El objetivo de la migración es explotación, no limpieza estética del esquema.

## Cierre del módulo `works`
- `works_song_name`: **cerrado** (70.370 A + 87 B/A aplicados; 191 preservados; 1.170 en revisión).
- `works_person_import` → `works_person_roles`: **cerrado** (2.540 materializaciones reversibles).
- `works_obra_iden`: **cerrado** como legacy/no utilizada.
- Sin referencias rotas ni inconsistencias detectadas.

**`works` cerrado.** No reabrir salvo inconsistencia concreta proveniente del bloque siguiente.
