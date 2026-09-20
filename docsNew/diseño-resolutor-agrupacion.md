# Resolutor de agrupación — nota de diseño

Estado: **implementado (2026-09-18)** como resolutor de solo lectura; **no** persiste la
resolución ni añade tablas. Ver §12.
Fecha: 2026-09-18 · Cierra el enfoque de `docsNew/diseño-semantica-representacion.md` (§9).

---

## 1. Objetivo

Convertir **recursos** en **representaciones** y **obras** mediante **agrupación/resolución
explícita**, indicando **por qué** se agrupan y **qué atributos** comparten.

No introduce un nivel persistente nuevo. `representations`/`works_resources` (tablas existentes) siguen
siendo el **inventario de origen**; la Representation y la Work que presentará el resolutor son
**agrupaciones virtuales** construidas a partir de los recursos.

## 2. Dos reglas generales

> **1. La identidad de la obra es autoritativa sobre los ejes de realización. Los ejes no pueden,
> por sí solos, crear una obra distinta.**

> **2. Los recursos son la evidencia persistente; las representaciones y las obras son
> agrupaciones inferidas por el resolutor.**

La segunda es deliberada: evita reinterpretar `representations` como un nivel ontológico
obligatorio de la BBDD.

## 3. Niveles y cadena

- **Resource** — dato **persistente** (fichero: MXL/PDF/MID…).
- **Representation** — **agrupación/resolución** de resources (inferida).
- **Work** — **agrupación/resolución** superior (inferida).

No hay un cuarto nivel. Los **ejes musicales** (voicing, ensemble, instrumentación, language,
key) son **criterios internos** para resolver la Representation, **no** un objeto.

```
RESOURCE
  │  evidencia persistente
  ▼
resolver
  ├── identidad de origen
  ├── metadatos (editor/licencia)
  └── ejes musicales
  ▼
REPRESENTATION      (agrupación inferida)
  │
  ▼
resolver
  ├── título
  ├── compositor
  ├── catálogo
  └── demás evidencia
  ▼
WORK                (agrupación inferida)
```

## 4. Criterios

| Nivel | Criterio | Papel |
|---|---|---|
| Resource → Representation | mismo `(origin, origin_id)` | **Identidad explícita de origen** (pesa más) |
| Resource → Representation | editor/licencia coincidentes | **Evidencia adicional**; sus diferencias **no bloquean** por sí solas |
| Resource → Representation | igualdad de voicing, ensemble, instrumentación, language, key | Criterio **interno**: confirma o separa **candidatos** |
| Representation → Work | título + compositor + catálogo + demás evidencia | **Identidad de obra** |
| Atributos comunes | intersección de valores; divergencias conservadas | **Resultado** de la agrupación |

### 4.1 Autoridad

- Misma obra + voicing distinto ⇒ **no** crea otra obra.
- Mismo título + mismo compositor + **catálogo distinto** (o evidencia de obras distintas) ⇒
  **no** se fuerzan a una misma obra aunque los ejes coincidan.

### 4.2 Qué hace una diferencia de ejes

Si dos recursos comparten `(origin, origin_id)`, esa **identidad de origen pesa más** que los
ejes. Una diferencia de voicing puede significar:

1. **dos realizaciones distintas**, o
2. un **dato contradictorio/incompleto que requiere revisión**.

Por eso el efecto de una diferencia de ejes es **separar candidatos de representación**, no
"separar representaciones" de forma automática.

### 4.3 Reglas que también deben explicarse: las que **impiden** una unión

El resultado incluye las **reglas de bloqueo** (por qué dos recursos/representaciones candidatos
**no** se unieron). Necesario para auditar casos que "parecen" el mismo.

## 5. Salida del resolutor

```
Resolver
  │
  ├── grupos
  │     ├── resources[]                    (recursos agrupados)
  │     ├── representation                 (agrupación inferida)
  │     └── work                           (agrupación inferida)
  │
  ├── reglas_aplicadas[]                   (por qué SÍ se unieron)
  │     ├── identidad_de_origen
  │     ├── evidencia_bibliografica
  │     └── ejes_musicales
  │
  ├── reglas_de_bloqueo[]                  (por qué NO se unieron)
  │     ├── catalogo_en_conflicto
  │     ├── compositor_no_coincide
  │     ├── evidencia_insuficiente
  │     ├── candidatos_ambiguos
  │     └── ejes_en_conflicto_revision
  │
  └── atributos
        ├── comunes[]                      (valor idéntico en todo el grupo)
        └── divergentes[]                  (valor por recurso)
```

Cada regla es **dato**, no solo log:

| Campo | Descripción |
|---|---|
| `rule` | identificador (p. ej. `origin_identity`, `work_identity`, `catalogue_conflict`) |
| `level` | `resource→representation` \| `representation→work` |
| `outcome` | `applied` (unió) \| `blocked` (impidió) \| `review` (requiere revisión) |
| `evidence` | valores concretos que la disparan (origin_id, títulos, catálogos, voicing…) |
| `explanation` | frase legible para UI/auditoría |

## 6. Catálogo inicial de reglas

**Aplicadas / de resolución:**

| id | Nivel | Dispara cuando | Efecto |
|---|---|---|---|
| `origin_identity` | R→Rep | mismo `(origin, origin_id)` | agrupa recursos (identidad fuerte) |
| `origin_metadata` | R→Rep | editor/licencia coinciden | **evidencia adicional** (su diferencia no bloquea) |
| `axes_confirm` | R→Rep | ejes iguales | confirma el candidato de representación |
| `axes_split` | R→Rep | algún eje difiere | **separa candidatos** de representación |
| `work_identity` | Rep→Work | título + compositor + catálogo (+ evidencia) coinciden | une representaciones en la misma obra |

**De bloqueo / revisión:**

| id | Nivel | Dispara cuando | Efecto |
|---|---|---|---|
| `catalogue_conflict` | Rep→Work | catálogos distintos | **no** une (aunque título/compositor coincidan) |
| `composer_mismatch` | Rep→Work | compositores distintos | no une |
| `insufficient_evidence` | Rep→Work | falta título o compositor normalizables | no une (queda como candidato) |
| `ambiguous_candidates` | Rep→Work | >1 obra candidata con evidencia equivalente | `review` |
| `axes_conflict_review` | R→Rep | mismo `origin_id` pero ejes incompatibles | `review` (no separa por sí solo) |

Nota: ningún eje musical puede emitir una regla de bloqueo a nivel de **Work**.

## 7. Entradas disponibles hoy

| Fuente | Datos |
|---|---|
| `works_resources` | `type`, `name`, `relative_path`, `status`, `file_id`, `url`, `archive_id` |
| `representations` | `origin`, `origin_id`, `origin_cpdlno`, `source_name`, `license` |
| `representation_persons` | editor (rol 6) |
| `works` | `title`, `catalogue`, `origin`… |
| `works_person_roles` | compositor (rol 1) |
| Ejes musicales | voicing/ensemble/instrumentación/language/key (hoy en `works`; CPDL a nivel de página) |

## 8. Bosquejo de algoritmo (conceptual)

1. **Recursos → Representation (origen)**: agrupar por `(origin, origin_id)` (`origin_identity`).
   Adjuntar `origin_metadata` (editor/licencia) como evidencia.
2. **Candidatos internos por ejes**: comparar ejes; `axes_confirm` mantiene, `axes_split` separa
   candidatos, `axes_conflict_review` marca revisión si la identidad de origen choca con los ejes.
3. **Representation → Work**: casar por identidad de composición (`work_identity`); ante
   conflicto, emitir la regla de bloqueo correspondiente y **no** unir.
4. **Atributos**: `comunes` = valor idéntico en el grupo; `divergentes` = valor por recurso.
5. **Salida**: grupos + reglas aplicadas + reglas de bloqueo + atributos.

Determinista y sin efectos: solo lectura. No escribe.

## 9. Casos de prueba previstos (para cuando se implemente)

| Caso | Esperado |
|---|---|
| CPDL: obra con 46 ediciones, **ejes iguales** | 1 Work + **1 Representation agrupada** + N Resources |
| CPDL: ediciones con **ejes distintos** | 1 Work + candidatos separados (`axes_split`) o `review` si el origen colisiona |
| Misma obra, voicing distinto | **1 Work**, candidatos de representación separados (revisables) |
| Mismo título+compositor, catálogo distinto | **2 Works** (`catalogue_conflict`) |
| MXL/PDF/MID de la misma edición | 1 Representation, 3 Resources |
| PDMX (1 score) | 1 Work, 1 Representation, 1 Resource |
| Título/compositor ausentes | candidato, sin unión (`insufficient_evidence`) |

## 10. No objetivos (ahora)

- **No** persistir la resolución ni añadir **otro nivel de BBDD**. Se persistirá solo si aparece
  una necesidad real: coste, revisión manual, historial o intervención humana.
- **No** unificar la tabla `works` ni retirar `archive_entries`/`cpdl_*`.
- **No** materializar recursos CPDL (etapa aparte).

## 11. Decisiones: estado (2026-09-18)

**Regla de identidad de compositor para `work_identity`** (sustituye a la decisión abierta de
normalización):

> La identidad de compositor para `work_identity` se determina mediante la **persona resuelta**
> (`person_id` / identidad canónica), **no** mediante comparación textual de nombres. Las
> variantes nominales solo sirven como **evidencia** para resolver esa identidad. Un compositor
> inequívocamente diferente **bloquea** la unión. La **ausencia o ambigüedad** de compositor no
> permite establecer por sí sola identidad de obra.

**Evidencia complementaria:**

> Título y catálogo actúan como **evidencia complementaria**. El **título genera candidatos**,
> pero **no** establece identidad de obra. Un **catálogo coincidente** puede reforzar una
> candidatura incluso sin compositor, pero **no** convierte por sí solo la ausencia de compositor
> en identidad demostrada.

| Decisión | Estado |
|---|---|
| Normalización de título | **Resuelta**: no es cuello de botella (lower/trim añade 0 buckets) |
| Identidad de compositor | **Resuelta**: persona resuelta, no texto |
| Compositor ausente | **Resuelta**: no fusionar automáticamente; candidato con evidencia insuficiente |
| Equivalencia de ejes | Pendiente |
| Umbral de ambigüedad | Pendiente |
| Exposición pública | Pendiente |

El motor **no se cambia** hasta cerrar la verificación de alias de §13.

---

## 12. Implementado (2026-09-18)

Resolutor de **solo lectura**, sin persistencia.

| Pieza | Archivo |
|---|---|
| Tipos (grupos, representaciones, reglas, atributos) | `domain/entities/resolution.py` |
| Servicio puro `resolve()` | `domain/services/grouping_resolver.py` |
| Puerto `ResolutionSource` | `domain/ports/resolution_source.py` |
| Evidencia SQL (read-only) | `infrastructure/repositories/sql_resolution_source.py` |
| Caso de uso `ResolveWorkGrouping` | `application/use_cases/resolution.py` |
| Endpoint admin | `GET /api/admin/resolution/works/{work_id}?candidate_limit=` |

Estructura devuelta: `groups[]` (obra inferida) → `representations[]` (agrupadas por eje) →
`resource_ids`; más `applied`/`blocked`/`review` (reglas con `evidence` y `explanation`) y
`attributes_common`/`attributes_divergent`.

Selección de candidatos: la obra semilla + obras con el **mismo `works_title` exacto** (la
normalización y el filtrado fino los hace el resolutor en memoria). El resolutor **no escribe**.

**Verificado en vivo** (`osap-storage`):

| Obra | Resultado |
|---|---|
| PDMX `1` | 1 grupo, **1 representación**, 1 recurso; `origin_identity`, `origin_metadata`; sin bloqueos |
| CPDL `262488` (Dido and Aeneas) | 1 grupo, **1 representación con 45 `source_keys` y 175 recursos**; `axes_confirm`, `work_identity`; divergentes: `license` (2), `editors` (4) |

Los 46 registros de edición CPDL se agrupan en **una sola representación** porque comparten los
ejes (voicing/ensemble/instrumentación son de la página), tal como fija §9.

**Pruebas**: 8 unitarias (`tests/domain/test_grouping_resolver.py`) + 4 de integración
(`tests/integration/test_resolution.py`) + 1 de endpoint. Suite completa **281 en verde**,
`ruff` limpio.

Pendiente de decisión: §11 (presentación pública del resultado; hoy solo endpoint admin) y la
normalización/umbral de §11.1–11.3.

---

## 13. Verificación previa a `work_identity` (2026-09-18)

Antes de tocar el motor se midieron las políticas de identidad sobre el conjunto real
(`scripts/analyze_composer_identity.py` → `docsNew/analisis-identidad-compositor.md`):

| Política | Grupos (143.379 obras candidatas) | Mergers | vs current |
|---|---|---|---|
| current (nombre normalizado) | 136.269 | 7.110 | — |
| A_strict (mismo `person_id`) | 136.266 | 7.113 | +3 |
| **B_tolerant** (persona canónica + variante por alias/`merged_into`) | **136.202** | **7.177** | **+67** |
| P0_block (ausente: nunca) | 136.266 | 7.113 | +3 |
| P1_catalogue (ausente: título+catálogo) | 136.201 | 7.178 | +68 |
| P2_sin_placeholders | 136.209 | 7.170 | +60 |

- Con compositor presente (150.142 pares): fusionan 11.858 (current) / 11.861 (A) / **12.154** (B).
- Con compositor ausente (387.467 pares): P0 **0**, P1 **1**, P2 **1** → la vía catálogo es
  irrelevante; el problema es de **cobertura de compositor** (177.024 obras sin resolver).

**Listado completo de alias de B** (`scripts/analyze_composer_identity.py`, verificación aparte):

- **28 pares de personas** con variante, **296 pares de obras**, **0 catálogos en conflicto**.
- Correctos: `J S Skinner = J Scott Skinner` (232 pares), `J S Bach = Johann Sebastian Bach` (14),
  `T O Carolan = Turlough O Carolan`, `L van Beethoven = Ludwig van Beethoven`,
  `G F HAENDEL = George Frideric Handel`, `F A Reissiger = Friedrich August Reissiger`…
- **Dudosos (3)**: `Franz Josef Haydn` vs `from Johann Michael Haydn` (son **personas distintas**),
  `P M G S McLennan` vs `Pipe Major John Macdonald Queens Own Cameron Highlanders`, y
  `Day s Psalter` vs `Days Psalter` (editorial, no persona). Provienen de `persons_aliases`, no de
  la lógica del resolutor.

Conclusión: **0 conflictos de catálogo**, condición pedida cumplida; pero el alias aporta ~3
enlaces incorrectos. `work_identity` no se modifica hasta decidir si B usa el alias tal cual o con
una comprobación de compatibilidad de nombre (iniciales/palabras) que descarte esos 3.

### 13.1 Corrección de datos aplicada (2026-09-18)

Las 3 colisiones eran filas concretas en **personas contaminadas** (no dos compositores distintos).
Se borraron 3 filas de `persons_aliases` en `osap-storage` y `osap-storage_test`:

| Alias borrado | Persona que lo tenía |
|---|---|
| `P.M. G.S. McLennan` (id 54815) | `Pipe Major John Macdonald…` |
| `Day's Psalter` (id 55175) | `Days Psalter` |
| `Franciscus Josephus Haydn` (id 2441) | `from Johann Michael Haydn…` |

Verificación tras la corrección: **25 pares de personas** (antes 28), **293 pares de obras**
(antes 296), **0 conflictos de catálogo**.

> Queda **pendiente de revisión manual** la contaminación de fondo: la persona
> `f1f53fb0…` ('from Johann Michael Haydn') aún conserva ~24 alias de **Joseph** Haydn, y
> `ca2fa567…`/`fa0cb050…` son registros duplicados/erróneos. No se tocaron más allá de las 3 filas.

### 13.2 `work_identity` modificado (2026-09-18)

`work_identity` ahora usa la **persona canónica** (`composer_id`, siguiendo `persons_merged_into`)
y las **variantes por alias** como evidencia; el texto del nombre ya no decide por sí solo.
`ResourceEvidence` incorpora `composer_id` y `composer_aliases` (los carga `SqlResolutionSource`).

**Efecto real** (motor ejecutado sobre los 40.500 buckets, `scripts/analyze_composer_identity.py`
y sweep del motor):

| Métrica | Antes (nombre) | Después (persona canónica) |
|---|---|---|
| Grupos | 136.269 | **136.205** |
| Mergers | 7.110 | **7.174** (+64) |
| `insufficient_evidence` (pares) | — | 106.958 |
| `composer_mismatch` (pares) | — | 129.259 |
| `catalogue_conflict` | 5 | 5 |
| `ambiguous_candidates` | — | 280 |

El resultado del motor (**136.205**) coincide exactamente con la política B medida en §13, lo que
valida la implementación. Suite completa **283 en verde**, `ruff` limpio.

---

## 14. Proveedor de evidencia RISM (contrato, 2026-09-18)

RISM actúa como **proveedor de evidencia de atribución** (read-only), no como diccionario de
nombres. No se persiste ninguna atribución; no se toca `persons`.

### 14.1 Contrato `100 $j` → estado de evidencia

| `$j` | Estado | ¿Resuelve compositor? |
|---|---|---|
| Verified | `resolved` | Sí |
| Ascertained | `inferred` | Sí, como inferencia |
| Conjectural | `ambiguous` | No automáticamente |
| Alleged | `ambiguous` | No automáticamente |
| Doubtful | `ambiguous` | No automáticamente |
| (sin `$j`) | `unclassified` | No |
| solo_nominal | `unclassified` | No |

> `resolved` **no** significa "RISM dice que es verdad", sino que hay evidencia externa
> suficientemente fuerte para que el resolver la considere atribución resuelta.

Solo `resolved` (y, según política, `inferred`) podrá entrar en `work_identity`; `ambiguous` va a
revisión; `unclassified` no es concluyente.

### 14.2 Matching endurecido (2A.1)

Conexión fuerte = **título uniforme `240`** OR **≥2 tokens significativos coincidentes**
(+ persona coincidente). Se excluyen títulos de **un solo token** significativo y tokens
**genéricos** (Gavotte, Air, Mass, Allegro…). Conexiones solo por variantes triviales quedan
fuera de la automática (`solo_nominal_debil`).

### 14.3 Cifras definitivas (2A.3)

Dump de fuentes RISM: **1.565.667** registros; objetivos: 9.709 obras / 1.931 personas.
Informe: `docsNew/analisis-fuentes-rism.md`. Índice de personas: `docsNew/analisis-cobertura-rism.md`.

| Resultado | Obras |
|---|---|
| `conecta_fuerte` | **2.476** (vía 240: 824 · vía 245: 1.652) |
| `solo_nominal_debil` (excluido de automática) | 1.702 |
| `solo_nominal` | 4.329 |
| `sin_fuentes_rism` | 1.202 |
| `anonimo_rism` | **0** |

Estados de las conexiones fuertes: **resolved 234** · **inferred 868** · ambiguous 54 ·
unclassified 1.320.

**Lectura**: RISM aporta ~**1.102** atribuciones utilizables (234 resueltas + 868 inferidas) y
1.320 por clasificar, sobre el subconjunto de obras con candidato. Es evidencia real pero
**acotada**; no resuelve el grueso folk de PDMX (~142.000 sin candidato). Corroborar **anonimato**
exigirá otros campos (incipit/notas), no el título.

### 14.4 Estado de las fases

- **2B — medido** (read-only): `scripts/analyze_rism_person_matches.py` →
  `docsNew/analisis-rism-2b-autoridad.md`. De los 3.825 matches únicos: GND 2.686, VIAF 2.824,
  fechas 3.566 (nacimiento rellenable 2.414, muerte 2.224, **conflictos 124**), y **13.622 alias
  nuevos** en 2.670 personas. Sin escribir en `persons`.
- **2C — integrado** (read-only):
  - `domain/entities/composer_attribution.py` (`ComposerAttribution`, `state_for_reliability`).
  - `domain/services/title_evidence.py` (tokens significativos; endurecido 2A.1).
  - `domain/ports/composer_attribution_provider.py` + `SqlRismAttributionProvider`
    (lee `rism_sources`; degrada a sin evidencia si el índice no está).
  - `resolve(evidences, attributions)`: una atribución **usable** (`resolved`/`inferred`) aporta
    identidad de compositor → puede unir en `work_identity` (regla `rism_attribution`);
    `ambiguous` → `rism_ambiguous` (revisión); `unclassified` no se usa.
  - `ResolveWorkGrouping` carga atribuciones para obras sin compositor y las pasa al resolutor.
  - Tests: `tests/domain/test_grouping_resolver.py` (+6). Suite **289 en verde**, `ruff` limpio.
- **2C.1 — canonicalización de personas RISM** (antes de medir): `scripts/canonicalize_rism_persons.py`
  une personas RISM que comparten **GND o VIAF** (union-find determinista) y guarda
  `rism_persons.rism_canonical_id` (157.687 personas; **31 fusionadas**). El proveedor usa el id
  canónico (`COALESCE`) con degradación si la columna no existe. Tests: `tests/domain/test_rism_canonical.py` (+4).

**Pendiente**: medir el comportamiento real del resolutor con el índice `rism_sources` ya cargado
(comparativa sin/con RISM) antes de decidir cualquier escritura de autoridad.
