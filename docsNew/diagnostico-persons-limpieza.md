# Diagnóstico — limpieza de `persons` (2026-09-20)

Read-only. Módulo nuevo: calidad de los **nombres de persona** que entraron desde el texto de
obra (PDMX). 45.217 personas; **988 filas sospechosas**.

Fichero de trabajo: `G:\rism\persons_limpieza_dry_run.csv`
(columnas: `persons_id, persons_name, visible, obras, roles, motivos, mojibake_fix`).

## 1. Casos concretos señalados (localizados)

| Nombre almacenado | `persons_id` | obras | Problemas |
|---|---|---|---|
| `: Ferdinand David (1810 1873)and Friedrich Hermann (1828-1907)` | `9c19f507…` | 1 | signo inicial · **dos nombres pegados** · fecha con espacio |
| `: Hans Sitt (18501922)Paul Klengel (1854-1935)` | `1e24d0b1…` | 1 | signo inicial · **dos nombres pegados** · fecha sin guion |
| `: Hans Sitt (1850-1922)` | `963421b4…` | 5 | signo inicial · **ya existe persona equivalente** |
| `: Leopold Auer (1845-1930) violinCarl Friedberg (18721955)` | `ecbbc0ca…` | 1 | signo inicial · **dos nombres** · **rol en el nombre** (`violin`) · fecha sin guion |
| `Carl Friedberg` | `3ed7f775…` | 1 | ya existe persona equivalente |
| `: Max Schneider (1875-1967)Rudolf Steglich (1886-1976)` | `47722587…` | 1 | signo inicial · **dos nombres pegados** |
| `MAX Max Schneider` | `b74af960…` | 1 | prefijo basura `MAX` |
| `: Siegfried Flesch (1933-2007)` | `f4b794ea…` | 3 | signo inicial (el usuario lo citó como «Sigfrido») |
| `?By James Knight a Blindman?untitled in MS titled per above inscription` | `1a02fd4c…` | 1 | **frase**, no persona · `?` como delimitador |
| `Numerous settings see below` | `61aeb9f1…` | 1 | **no persona** |
| `?Raisin Band?` | `3d553f2e…` | 3 | no persona (banda) |
| `(trad.)` | — | **1.772** | placeholder con muchísima obra |
| `(attributed to) Jeremiah Ingalls 1764-1828` | — | 178 | placeholder + persona real mezcladas |
| `(Attributed to) G major Amzi or Lucius Chapin` | — | 63 | placeholder + **dos personas** (`or`) |
| `Tradicional ?` | — | **631** | placeholder + `?` |

**No localizados** (no existen en `persons` ni en `works_person_import`, búsqueda laxa incluida):
`¡¡Vaya a la configuración!!`, `¿Número 12?`, `¿Número 17?`, `¿Número 32?`, `¿Banda de pasas?`.
Proceden de otra pantalla/fuente: falta identificar la vista que los muestra.

## 2. Clasificación global (988 filas, solapan motivos)

| Motivo | Filas | Naturaleza | Tratamiento propuesto |
|---|---|---|---|
| `signo_inicial` | 320 | prefijo `: `/`;`/`«`/`¿`/`¡` delante de un nombre real | **limpiar prefijo** (y **merge** si ya existe el nombre limpio) |
| `mojibake` | 244 | UTF-8 destruido (`Ð…`), p. ej. cirílico | **irrecuperable** desde la BBDD → re-importar de la fuente |
| `nombres_pegados` | 170 | 2+ nombres sin separador (`)and`, `)Paul`, `)Rudolf`) | **dividir** → decisión por obra |
| `frase` | 113 | `Untitled in MS`, `MS 38 p 140`, `No Wm Clarke MS…` | **no son personas** → `persons_visible = 0` |
| `interrogacion` | 89 | `Tradicional ?`, `Trad. Irish?` | revisar (mezcla placeholder + real) |
| `sin_letras` | 51 | `1728`, `1750`, ids | **no son personas** → `persons_visible = 0` |
| `punto_y_coma` | 47 | `X; Y` → dos personas | **dividir** |
| `fecha_mal_formada` | 9 | `(18501922)` en vez de `(1850-1922)` | **corregir guion** (mecánico) |
| `placeholder` | 4 | `(trad.)`, `(attributed to)…` | decisión de producto (ver §4) |
| `no_persona` | 1 | `Numerous settings see below` | `persons_visible = 0` |

## 3. Codificación (respuesta al «quizá uses otra codificación»)

- BBDD y conexión: `utf8mb4` / `utf8mb4_unicode_ci`; el cirílico **sí** se almacena bien en otros
  casos (`Александр Архангельский`, 27 obras; `周杰倫`, 9).
- Las 244 filas mojibake perdieron bytes en origen: `ÐÐ3⁄4Ñ…` no se recupera con
  `cp1252/latin1/mac_roman → utf8` ni recomponiendo fracciones NFKC (`1⁄2`→`½`): **solo 3 de 244**
  se reparan. Conclusión: hay que **releer el nombre de la fuente** (metadatos PDMX/MuseScore de la
  obra), no reinterpretar la cadena.
- Los `?` de tu captura son, en unos casos, `?` literales (89 filas) y, en otros, el render de ese
  mojibake.

## 4. Decisiones (estado)

1. **`persons_visible = 0`** para `frase` + `sin_letras` + `no_persona` — **DECIDIDO Y APLICADO**
   (216 filas; ver §7). Es el mecanismo ya usado por los merges y oculta de listados y desplegables
   sin borrar ni romper FK.
2. **`placeholder`** (4 filas, 2.015 obras) — **DECIDIDO**: no debía crearse persona; se marca la
   **obra** con `works_attr_type` (`TRADICIONAL` / `ATRIBUIDA`) + `works_attribution_note` (ver §8).
   **Pendiente de ejecutar.**
3. **`nombres_pegados` (170) + `punto_y_coma` (47)** — **PENDIENTE**: dividir exige decidir el rol
   de cada parte (p. ej. Ferdinand David compositor vs Friedrich Hermann artista) → revisión
   dirigida, no automática (fase 2).
4. **`signo_inicial` (~320)** — **PARCIALMENTE APLICADO**: 10 prefijados sin colisión ya se
   limpiaron (§7); el resto son pares pegados/bloques de crédito que van a la fase 2, y algunos
   podrían requerir **merge** con `persons_merge_history` + snapshot, como el Lote 1A.
5. **`mojibake` (244)** — **PENDIENTE**: re-importar el nombre desde la fuente de la obra.
6. **Bandas/ensembles con nombre** — **DECIDIDO**: son **artistas** y se quedan en `persons`
   (ver §7, «Criterio de ensembles»).

## 5. Pendiente de identificar (resuelto)

Las 5 cadenas de la lista del usuario **sí estaban en la BBDD**, en inglés; ver §6.

---

## 6. Resuelto: los ejemplos «desaparecidos» estaban en inglés

Los casos que no encontraba (`¿Número 12?`, `¡¡Vaya a la configuración!!`, `¿Banda de pasas?`) **sí
están en `persons`**, pero en inglés y, en algún caso, con el prefijo de signos:

| Lo que viste | Lo almacenado |
|---|---|
| ¿Número 12? / 17 / 32 | `'No 12'`, `?No 32?` |
| ¡¡Vaya a la configuración!! | `!! Go to stettings` (typo de *settings*) |
| ¿Banda de pasas? | `?Raisin Band?` |

La causa de no localizarlos fue buscar el texto en español; se reclasificaron como **no-persona**.

---

## 7. Fase 1 aplicada y verificada (2026-09-20)

Script: `scripts/cleanup_persons_phase1.py` (dry-run por defecto; `--apply`; `--revert <batch>`).
Auditoría: `persons_correction_history` (`operation='correct'|'revert'`, `before_json`/`after_json`,
batch en `reason`). Plan: `G:\rism\persons_fase1_plan.csv`.

| Acción | Filas | Detalle |
|---|---|---|
| `ocultar` (`persons_visible = 0`) | **216** | frases (`Untitled in MS`, `MS 38 p 140`…), sin letras (`1728`), no-persona (`Numerous settings…`, `!! Go to stettings`, `'No 12'`, `Violetta Banda Sonora`) |
| `renombrar` | **10** | se quita el prefijo `:`/`'`/`?` y se arregla la fecha: `: Hans Sitt (1850-1922)`→`Hans Sitt (1850-1922)`, `'Femi Adeogun`→`Femi Adeogun`, `?Raisin Band?`→`Raisin Band`, `: All Time Low ft. Vic Fuentes`→`All Time Low ft. Vic Fuentes`, `Charles Winfred Douglas (18671944)`→`…(1867-1944)` |
| `diferido` | **10** | pares pegados, bloques de crédito con 2-3 personas (`Georges Bizet(18381875)arr. …`), `? Revised by David Charlier` |
| `placeholder` | **4** | van por `works_attr_type` (ver §8) |

Estado:

| | Antes | Después |
|---|---|---|
| `persons_visible = 1` | 44.740 | **44.524** |
| `persons_visible = 0` | 477 | **693** |
| `persons_correction_history` | 1 | **721** |

Ciclo `apply → verify → revert → verify → apply → verify` correcto (el revert restaura 44.740/477 y
los nombres originales). `ruff` limpio · **298 tests** en verde.

### Criterio de ensembles (corregido el 2026-09-20)

**Una banda/ensemble con nombre propio es un artista → se queda en `persons`** (`Zac Brown Band`,
`The Dave Brubeck Quartet`, `The Kingston Trio`, `Electric Light Orchestra`…; roles 1/10). El
primer intento de la fase 1 las ocultó por la regla `\bBand\b`: se detectó, se revirtió el batch y
se re-aplicó **sin** esa regla. Verificado que las 10 bandas de muestra quedan `visible = 1`.

Lo que **sí** es no-persona son las frases con la palabra *band/choral* incrustada
(`O happy band of pilgrims - Barnby`, `Violetta Banda Sonora`, `A. Klengel Kanons und Fugen Band`
—*Band* = volumen en alemán—), que siguen ocultas.

`ensembles` (código UNIQUE + `ensemble_voices`) queda como catálogo de **tipos/configuraciones**
(`SATB`, `SSAA`, `BAND`…), no de agrupaciones con nombre; por eso **no** se movió nada a esa tabla:
el intento falló con `Duplicate entry 'BAND'` y **no dejó estado parcial** (360 filas de `ensembles`
y 96.305 de `work_ensembles` intactas). La columna `ensembles_type` que llegué a añadir como
migración `002` se **revirtió** (columna e índice eliminados en `osap-storage` y
`osap-storage_test`, entrada borrada de `schema_migrations`).

---

## 8. Placeholders: mecanismo previsto encontrado

`works` tiene **`works_attr_type`** (comentario: `ANONIMA, TRADICIONAL, POPULAR, ATRIBUIDA`) y
**`works_attribution_note`**. Es decir, el diseño ya preveía marcar la **obra** y **no crear
persona** para `(trad.)`, `(Trad. Germany)`, `(attributed to) …`.

Propuesta para los 4 placeholders (2.015 obras):
- `(trad.)` / `(Trad. Germany)` → `works_attr_type = 'TRADICIONAL'` (+ nota `Germany` si aplica).
- `(attributed to) Jeremiah Ingalls 1764-1828` → `ATRIBUIDA` + `works_attribution_note` con el
  nombre (no se crea persona).
- `(Attributed to) G major Amzi or Lucius Chapin` → `ATRIBUIDA` + nota (atribución ambigua).

Después, esas 4 personas placeholder pasan a `persons_visible = 0` (ya no son la vía de atribución).

