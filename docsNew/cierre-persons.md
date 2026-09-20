# Cierre del módulo `persons` — informe de estado (2026-09-19)

## 1. Lote 1A ejecutado y verificado

7 merges (Grupo A) ejecutados con `scripts/execute_merge_1a.py`, auditados y reversibles:

| Origen | Destino | roles movidos | dedupe (snapshot) |
|---|---|---|---|
| Arranged from Beethoven (1770-1827) | Ludwig van Beethoven | 5 | identidad ×1 |
| From Beethoven | Ludwig van Beethoven | 5 (1 alias) | identidad ×1 |
| Arranged from Beethoven | Ludwig van Beethoven | 1 | identidad ×1 |
| from Beethoven (1770-1827) | Ludwig van Beethoven | 5 | identidad ×1 |
| Arranged from Haydn (1732-1809) | Joseph Haydn | 2 (rol 3) | **wpr ×2 (colisión rol 1) + identidad ×2** |
| Arranged from Schubert Op. 140 | Franz Schubert | 2 | identidad ×2 |
| Arr Alexander Maltas | Alexander Maltas | 1 | identidad ×1 |

- **Ciclo probado**: apply → verify → **revert** → verify → apply → verify.
- Tras el merge: orígenes con `persons_merged_into=target`, `wpr=0`; destinos sin duplicar
  (`Beethoven 1:308,3:7,10:377`; `Haydn 1:499,3:4,10:313`; `Schubert 1:338,3:1,10:228`;
  `Maltas 1:4,3:1`).
- **Revert deja el estado previo exacto** (orígenes restaurados, historial y snapshots a 0).
- **Auditoría**: `persons_merge_history` (7) + `persons_merge_snapshot` (7 con `moved`/`deleted`).
- Incidencia corregida: `persons_merge_history.merge_operation_id` es `char(36)` → ahora se usa
  **UUID4** (antes se truncaba y el revert no borraba el historial).

## 2. Resto de las 404 personas prefijadas

| Grupo (mapa v2) | Personas | Tratamiento |
|---|---|---|
| `duplicado_seguro` | 50 | 7 en Lote 1A (hecho) · 2 en revisión (Grupo B) · **41 fuera**: 17 `sin_evidencia`, 16 `identidad_dudosa`, 8 `destino_inadecuado` |
| `duplicado_variante` | 115 | **review** (candidatos + evidencia en `G:\rism\identity_map_v2.csv`) |
| `sin_destino` | 68 | **rename** in-situ candidato (revisión) |
| `no_persona` | 164 | metadata 146 · fuente/colección 13 · obra 5 → **no son personas** (no merge) |
| `ambigua` | 4 | revisión manual |
| `descartado_no_resoluble` | 3 | pendiente |

**No quedan merges automáticos seguros** bajo las reglas establecidas (exacto/alias/identificador,
destino completo, sin conflicto). Los casos restantes dependen de fuzzy, iniciales o apellido → van a
revisión.

### Casos explícitamente fuera
- `Arr : Iraj Goli` → `iraj goli` (destino sin rol 1) → **review**.
- `Edited byJAY YOUNG` → `Jay Young` (destino sin obras) → **review**.
- Falsos negativos dirigidos: `from P.P. Bliss` → `Philip Paul Bliss (1838-1876)` y
  `Arr from Johann Michael Haydn` → `Michael Haydn` (requieren regla dirigida; no fuzzy automático).

## 3. Atribuciones RISM (no se tocan)

- **94 asignaciones live** (BATCH1 42 · BATCH2 52), en `work_attribution_history` (`operation='assign'`),
  reversibles.
- Corrección de Joseph Haydn (`persons_correction_history`) intacta; 3 alias de Michael trasladados a
  `96714c71…`.

## 4. Integridad

- Sin referencias rotas: `works_person_roles` no es referenciada por otras tablas.
- Sin duplicaciones: las colisiones se deduplican con snapshot.
- Todo cambio auditado: `persons_merge_history`, `persons_merge_snapshot`,
  `persons_correction_history`, `work_attribution_history`.

## 5. Criterio de cierre

| Criterio | Estado |
|---|---|
| Merges claramente seguros pendientes | **ninguno** |
| Duplicados peligrosos | en `review` (variante 115 · ambigua 4 · Grupo B 2) |
| No-persona | clasificados (164) — no se convierten en personas |
| Sin identidad | identificados (`sin_destino` 68) |
| Merges auditables y reversibles | sí (probado) |
| Referencias rotas / inconsistencias | ninguna detectada |

**`persons` queda suficientemente cerrado.** Los 404 prefijados no contienen más merges automáticos
seguros; el resto queda en revisión con su evidencia registrada.
