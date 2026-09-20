# §11 — Semántica de Representation (decisión de modelo)

Estado: **§11 cerrado (2026-09-18)**: D1, D2, **D3 = Opción A**, D4, y **sin nuevo nivel
persistente** (§9). No se cambia esquema ni datos.
Fecha: 2026-09-18 · Base: casos reales ya en la BBDD. Continúa
`docsNew/diseño-representaciones-recursos.md` (§11).

---

## 1. La pregunta

¿Qué es exactamente una **Representation** y **cuándo** una obra necesita más de una?

Hasta ahora solo teníamos un caso trivial (`obra → archivo MusicXML`). Con el corpus actual ya
hay casos reales que permiten fijarlo.

## 2. Evidencia (BBDD `osap-storage`)

| Hecho | Valor |
|---|---|
| PDMX: obras con >1 representación | **0** (254.035 obras, 1 `score` cada una) |
| CPDL: obras con ≥2 ediciones | **13.644** (8.740 con 2, 2.288 con 3, … hasta 50) |
| CPDL: obras con ediciones de **distinto editor** | **8.540** |
| CPDL: obras con ediciones de **distinta licencia** | **6.036** |
| CPDL: voicing / instrumentación | a nivel de **página** (56.420 de 56.420), **no** por edición |
| CPDL: por edición solo se captura | `cpdlno`, `license`, `editor`, `files` |
| PDMX: `work_parts` | 408.971 filas (250.256 obras; media 1,63; máx 64) |
| CPDL: `work_parts` | **0** |
| `works.works_obra_iden` (auto-referencia) | **0 usos** |
| Duplicados exactos PDMX∩CPDL (título+compositor) | **182** pares |

Dos conclusiones de partida:
- La multiplicidad **real** de representaciones existe y viene de CPDL (ediciones), y se
  distingue por **editor/licencia/conjunto de ficheros**.
- El **Work sigue siendo específico de fuente** (PDMX hash vs página CPDL); no hay unificación
  entre fuentes (`works_obra_iden` sin usar; solo 182 coincidencias exactas). Por tanto la
  multiplicidad *entre fuentes* **no** es el problema de hoy.

## 3. Definición propuesta

> **Representation** = una **realización** concreta de una obra: el acto editorial/musical que la
> fija (edición de un editor, versión, arreglo, transcripción, fuente). Se identifica por
> `(origin, origin_id)` y lleva sus propios **licencia** y **editor**.
>
> **Resource** = una **codificación digital** de esa representación (MXL, PDF, MIDI, MP3…).

Corolario: **los ficheros no crean representaciones**. MXL + PDF + MID de la misma edición son
**1 representación con 3 recursos** (PDMX los publica así; hoy solo se importó `mxl.tar.gz`).

## 4. Cuándo hace falta más de una (regla)

Una nueva Representation es necesaria cuando cambia un **eje de realización**:

| Eje | Ejemplo real | ¿Nueva representación? |
|---|---|---|
| Acto editorial (editor / edición / licencia) | CPDL: 8.540 obras con >1 editor | **Sí** |
| Realización musical (voicing, ensemble, instrumentación, transposición, arreglo) | arreglo para otro coro o instrumento | **Sí** |
| Fuente / plataforma (PDMX, CPDL, IMSLP…) | misma obra en PDMX y CPDL | **Solo si el Work se unifica**; hoy no ocurre |
| Codificación del mismo hecho (MXL/PDF/MID) | misma edición en 3 formatos | **No** → recursos |
| Metadatos derivados (título, catálogo, género) | — | **No** |

## 5. Dónde van `voicing` y `work_parts`

Evidencia: el voicing de CPDL se capturó a **nivel de página**, igual para todas las ediciones de
la obra; PDMX no tiene voicing. `work_parts` solo existe para PDMX y procede del **fichero
MusicXML** (lista de partes del score; los PDF no tienen partes).

**Opción A — elegida (D3, 2026-09-18):**
- **Representation** posee los atributos de **realización**: `voicing`, `ensembles`,
  `instrumentación`, `language`, `key` (+ licencia/editor que ya tiene).
- **Resource** posee la **lista de partes** (`work_parts`), porque es una propiedad del fichero
  de score; se agrega para mostrar por representación/obra.
- **Work** conserva identidad y metadatos de la composición (título, catálogo, género, época,
  compositor…).

**Opción B (lazy):** dejar voicing/`work_parts` en `Work` y no mover nada hasta que aparezca una
segunda realización con distinto voicing. Menos trabajo ahora; no modela arreglos y deja el
atributo en el nivel equivocado.

**Opción C (híbrida):** mover voicing/ensemble/language/instrumentación a Representation y
mantener `work_parts` en Work. Evita tocar `work_parts`, pero deja las partes en el nivel de la
obra aunque provengan del fichero.

Nota honesta: con los datos actuales, mover el voicing a Representation **no discrimina** las
ediciones CPDL (el valor se copiaría de la página a cada edición). El valor de la Opción A es de
**modelo** (permite arreglos y unificación futura), no de datos de hoy.

## 6. Fronteras (lo que NO decide esta nota)

Se mantienen separados, como pediste:
- **Materialización de CPDL** — cómo un recurso de inventario pasa a descargable (URL derivada vs
  descarga propia) y con qué licencia. No cambia la definición de Representation.
- **Retirada de `cpdl_*`** — las tablas de staging siguen hasta que la migración esté validada.
  No afecta a la semántica.

## 7. Decisiones confirmadas (2026-09-18)

1. **D1 — confirmado** — Representation = *realización* identificada por `(origin, origin_id)` con
   licencia y editor propios (§3).
2. **D2 — confirmado** — Multiplicidad por los tres ejes de §4 (editorial, realización musical, y
   fuente solo si se unifica el Work).
3. **D3 — Opción A** — `voicing`/`ensembles`/`instrumentación`/`language`/`key` → **Representation**;
   `work_parts` → **Resource**; Work conserva identidad y metadatos (§5).
4. **D4 — confirmado** — Materialización CPDL y retirada de `cpdl_*` se tratan en notas/etapas
   aparte (§6).

Estructura fijada:

```
Work                 (identidad y metadatos de la obra)
 └── Representation  (realización: voicing, ensemble, instrumentation, language, key, licencia, editor)
      └── Resource   (codificación: MusicXML, PDF, MIDI… + work_parts)
```

Aclaración (2026-09-18): "realización" **describe lo que agrupa** la Representation; **no** es un
nivel aparte. Solo hay tres niveles: `Resource` (persistente), `Representation` y `Work`
(agrupaciones inferidas). Los ejes musicales son criterios internos de la resolución.

## 8. Plan de implementación (etapa posterior, sin ejecutar)

- **Datos**: para cada representación, copiar los atributos de realización desde su obra
  (CPDL: voicing/instrumentation/language/ensembles de la página) y dejar los recursos con sus
  partes (PDMX). Migración aditiva, sin retirar columnas actuales de `works` hasta validar.
- **App/DTO**: exponer `voicing`/`ensembles`/`instrumentación`/`language`/`key` por representación
  y las partes por recurso, agregando para la vista de obra.
- **Verificación**: obras CPDL multi-edición (46 casos) y PDMX con partes (máx 64) como pruebas
  de regresión.
- Nada de esto se toca hasta confirmar D1–D3.

---

## 9. Cierre de §11: resolución por agrupación, no nuevo nivel persistente (2026-09-18)

**No se crea otro nivel persistente.** El sistema trabaja por **resolución/agrupación**:

```
RESOURCE
  ↓  agrupación / resolución  (¿por qué se agrupan?)
REPRESENTATION
  ↓  agrupación / resolución
WORK
```

- `representations` / `works_resources` (tablas ya creadas) se mantienen como **inventario/agrupación de
  origen**: lo que la fuente declara (edición CPDL, score PDMX). **No** obligan a que la
  Representation presentada sea exactamente esa fila.
- La **Representation que se presenta** puede ser una **construcción posterior sobre los
  recursos** (agrupación explícita + atributos comunes), no una entidad persistente nueva.
- **Work** es, igualmente, un **nivel de presentación/resolución** en la parte alta del pipeline.

Consecuencia práctica: **no más migraciones** para resolver una distinción conceptual que puede
resolverse mediante agrupaciones. La estructura de §7 describe el **modelo de presentación**, no
una obligación de persistir `voicing`/`work_parts` en tablas nuevas.

### 9.1 Etapa siguiente (sin ejecutar)

Diseño detallado del resolutor, con criterios, autoridad, salida (grupos + reglas aplicadas y de
**bloqueo** + atributos comunes/divergentes) y casos de prueba:
**`docsNew/diseño-resolutor-agrupacion.md`**.

Construir un **resolutor de agrupación** que:
1. Agrupe Resources de forma **explícita**.
2. **Explique por qué** los agrupa (regla/evidencia: mismo `origin_id`, mismo editor, mismos ejes
   de realización…).
3. **Calcule qué atributos son comunes** (voicing, ensemble, instrumentación, language, key,
   licencia) y cuáles difieren.
4. Exponga Representation/Work como **resultado de la resolución**.

Persistir esa resolución (por coste, revisión manual, historial o intervención humana) queda como
decisión **condicionada**: solo si aparece esa necesidad real.
