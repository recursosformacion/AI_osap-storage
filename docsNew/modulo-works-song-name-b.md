# Módulo `works` — cierre de `works_song_name` (2026-09-19)

Filosofía: diagnóstico → clasificación → dry-run → ejecución reversible → verificación → cierre.

## Subconjunto A (70.370) — ya aplicado
Sin separador o sufijo no-persona → `song_name = works_title`. Ver `modulo-works-song-name.md`.

## Subconjunto B (1.448) — clasificado y parcialmente aplicado

Regla endurecida: persona = **conocida** (`persons`/alias); `A` exige sufijo == compositor (rol 1) o
sufijo-persona + prefijo corroborado; `B` conserva patrón `compositor - título` y marcadores de
dedicatoria/estilo.

| Clase | Casos | Tratamiento |
|---|---|---|
| **A — recorte seguro** | **87** | **aplicado** (reversible) |
| **B — mantener título completo** | 191 | sin cambios |
| **C — revisión** | 1.170 | pendiente de revisión semántica |

Dry-run: `G:\rism\works_song_name_B_dry_run.csv` · informe `docsNew/dry-run-works-song-name-B.md`.

### Ejecución reversible de los 87 (`scripts/apply_song_name_b.py`)
- Validación previa contra la BBDD: **0 mismatches** (aborta si cambia).
- Solo se modifica `works_song_name`; valor previo guardado en `works_field_history`
  (`operation='strip'`, `batch_id`); revert exacto.

| | `song_name` vacíos | historial |
|---|---|---|
| Previo | 1.448 | fill 70.370 |
| apply | **1.361** | fill 70.370 + **strip 87** |
| revert | 1.448 | fill 70.370 |
| re-apply | **1.361** | fill 70.370 + strip 87 |

`apply → verify → revert → verify → apply → verify` correcto; los otros 1.361 intactos; `ruff` limpio.

## Cierre de `works_song_name`
- **70.370 A** aplicados · **87 B/A** aplicados · **191 B** preservados · **1.170 C** en revisión.
- Total rellenado: **70.457**. Reversible vía `works_field_history`.

## Siguiente en `works`
- `works_obra_iden` (**0 usos**) → documentar y cerrar el aspecto.
