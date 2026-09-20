# Módulo `works` — sub-módulo `works_song_name` (2026-09-19)

Filosofía: diagnóstico → dry-run → ejecución → verificación → cierre.

## Diagnóstico
- `works`: 254.035 PDMX + 56.420 CPDL. Con compositor (rol 1): 133.525 · sin compositor 176.930.
- **`works_song_name` vacío: 71.818** · `works_title` con `" - "`: 68.047 · `title≠song_name`: 86.447.
- 69.410 vacíos **no** tienen separador `" - "` (su `works_title` ya es el título limpio).

## Dry-run (`scripts/propose_song_name.py`)
- 71.818 vacíos → **71.818 propuestas**, divididas:
  - **A seguro (70.370)**: sin separador (69.410) + sufijo no-persona (960) → `song_name = works_title`.
  - **B revisar (1.448)**: sufijo = compositor (59) o persona (1.389) → `song_name = prefijo` (requiere revisión: hay títulos con compositor delante).

## Ejecución (`scripts/apply_song_name.py`, solo A)
- `apply` → 70.370 filas + `works_field_history` (batch UUID).
- `revert` → restaura (song_name vacío 71.818; historial 0).
- Ciclo probado: **apply → verify → revert → verify → re-apply → verify**.

| | Vacíos `song_name` | Historial |
|---|---|---|
| Antes | 71.818 | 0 |
| Tras apply | **1.448** | 70.370 |
| Tras revert | 71.818 | 0 |
| Tras re-apply | **1.448** | 70.370 |

## Cierre
- `works_song_name` completado en el subconjunto seguro (A). Reversible vía `works_field_history`.
- **Pendiente B (1.448)**: sufijo compositor/persona → revisión (riesgo de recortar títulos con
  compositor al inicio, p. ej. `Peter I. Tchaikovsky - Italian Song…`).

## Siguientes en el módulo `works`
1. B (1.448) → revisión dirigida.
2. Obras sin compositor (176.930; 172.701 con `works_person_import`) → enlace import↔persons.
3. `works_obra_iden` sin usar.
