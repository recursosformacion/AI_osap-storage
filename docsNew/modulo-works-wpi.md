# Módulo `works` — sub-módulo `works_person_import` → `works_person_roles` (2026-09-19)

Filosofía: diagnóstico → clasificación → dry-run → ejecución reversible → verificación → cierre.

## Diagnóstico / semántica
- `works_person_import` es **staging de nombres importados** (PDMX), no una atribución nueva.
- `resolved=1` = **ya materializado**; `2` = pendiente; `0` = ruido. Evidencia: composer resolved=1
  → **133.345/145.387** obras con rol 1; artist resolved=1 → **74.669/77.766** con rol 10; resolved=2
  → 0 con rol.
- Relación canónica confirmada por precedente: **`composer` → rol 1**, **`artist` → rol 10**.

## Dry-run (`scripts/plan_wpi_materialization.py`, solo nombre único y válido)

| Resultado | composer | artist |
|---|---|---|
| ya tiene el rol | 133.356 | 74.669 |
| **propuesta** | **1.790** | **750** |
| sin match | 11.839 | 162.893 |
| múltiple | 0 | 132 |
| inválido | 387 | 188 |

**Total: 2.540** (CSV `G:\rism\wpi_materializacion.csv`).

## Ejecución reversible (`scripts/execute_wpi_materialization.py`)
- Validación previa contra la BBDD: **0 mismatches** (aborta si el CSV queda obsoleto).
- Auditoría: `works_person_roles_history` (`operation='assign'`, `batch_id`), con
  `works_person_roles_id` para revert exacto.
- Sin crear personas; sin tocar `works_person_import` (marcar `resolved=1` queda opcional/posterior).

| | rol 1 | rol 10 | historial |
|---|---|---|---|
| Previo | 134.466 | 74.669 | 0 |
| apply | **136.256** (+1.790) | **75.419** (+750) | 2.540 |
| revert | 134.466 | 74.669 | 0 |
| re-apply | **136.256** | **75.419** | 2.540 |

Ciclo `apply → verify → revert → verify → apply → verify` correcto. `ruff` limpio.

## Cierre
- Submódulo **cerrado**: 2.540 materializaciones auditadas y reversibles; 0 colisiones; ninguna
  persona nueva; ningún vínculo preexistente alterado.
- Fuera: 174.732 filas sin match / ambiguas / inválidas / ya materializadas.

## Siguiente en `works`
1. `works_song_name` **B (1.448)** — revisión semántica de títulos.
2. `works_obra_iden` (0 usos) — documentar/cerrar.
