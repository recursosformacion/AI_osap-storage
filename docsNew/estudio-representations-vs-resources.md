# Estudio: `representations` vs. campos en `works_resources`

Read-only. Datos de `osap-storage` (2026-09-19). Objetivo: valorar si la tabla `representations`
aporta algo **en volumen** y **en coste de trabajo**, frente a poner sus campos en
`works_resources`, incluyendo un escenario de **+1M registros RISM**.

## 1. Estado actual

| Tabla | Filas | Datos | Índices | Total | ≈ bytes/fila |
|---|---|---|---|---|---|
| `representations` | 336.018 | 45,6 MB | 48,7 MB | **94,3 MB** | **303** |
| `representation_persons` (editores) | 80.166 | 8,5 MB | 13,6 MB | **22,1 MB** | 289 |
| `works_resources` | 471.378 | 71,6 MB | 29,5 MB | 101,2 MB | 225 |
| `works` | 310.455 | 96,7 MB | 36,7 MB | 133,3 MB | 451 |
| **Total BBDD** | | | | **1.969 MB** | |

`representations` = **4,8 %** de la base.

## 2. ¿Cuánto ahorra la tabla? (duplicación evitada)

Campos que la tabla guarda una vez por edición:
`representations_origin + _origin_id + _license + _source_name + _type + _origin_cpdlno`.

| | MB | Filas |
|---|---|---|
| Campos en `representations` (1×/edición) | **23,76** | 336.018 |
| Los mismos campos duplicados en `works_resources` | **28,32** | 471.378 |
| **Ahorro real por duplicación** | **4,56 MB** | |

¿Por qué tan poco? Porque el ahorro solo existe cuando una edición tiene **varios** ficheros:

| Origen | Representaciones | Recursos | Recursos/edición |
|---|---|---|---|
| PDMX | 254.035 | 254.035 | **1,00** (sin ahorro) |
| CPDL | 81.983 | 217.343 | **2,65** (máx. 225) |

El 75 % de las representaciones (**254.035 PDMX**) son **1:1 con `works`**: `origin_id = works_key`
y `license = works_license`, datos que **ya están en `works`**. Solo las **81.983 ediciones CPDL**
llevan datos propios (licencia y editores por edición).

> **La tabla cuesta 94,3 MB para ahorrar 4,56 MB** (~20× más caro que la duplicación que evita).
> El volumen **no** justifica `representations`.

## 3. Coste si se disuelve (campos → `works_resources`)

| Concepto | MB |
|---|---|
| + campos duplicados en `works_resources` | +4,56 |
| + índice `(origin, origin_id)` en `works_resources` (para agrupar; hoy en `representations`) | ≈ +30 |
| − tabla `representations` | −94,3 |
| − reubicar `representation_persons` (editan por edición; seguiría necesitando un ancla) | ≈ 0 a −22 |
| **Neto estimado** | **≈ −55 a −85 MB** |

No es una ganancia grande (3–4 % de la BBDD), pero es **positiva**.

## 4. Coste en tiempo (join)

Medición directa (5.000 filas, media de 5):

| Consulta | ms |
|---|---|
| `SELECT … FROM works_resources` | 66,4 |
| `SELECT … FROM works_resources JOIN representations` | 78,6 |
| **Sobrecoste del join** | **+18 %** |

Con índices, el join es una búsqueda por PK por fila: no es dramático, pero **toda** lectura con
contexto de edición (licencia/origen/editor) y toda escritura pagarán ese salto extra, y el código
tiene dos entidades que mantener sincronizadas.

## 5. Escenario +1M registros RISM

RISM son **metadatos sin fichero** (1.565.667 fuentes; p. ej. 1M a incorporar).

| Opción | Filas nuevas | Volumen |
|---|---|---|
| **Con `representations`** (1 rep por fuente, 0 recursos) | +1M reps | **+≈300 MB** (a 303 B/fila) pagando filas **sin fichero** |
| **Sin `representations`** (campos de origen/licencia en `works`) | +0 reps | **+≈55 MB** (a ~55 B de campos en `works`) |

Diferencia a favor de **no** tener `representations`: **≈ 250 MB** en 1M registros (y crece lineal).

## 6. Conclusión

- **Volumen**: `representations` **no se justifica** — cuesta ~20× lo que ahorra hoy, y con RISM
  1:1 empeora ~5× (~250 MB por 1M). El 75 % (PDMX) es redundante con `works`.
- **Tiempo**: +18 % en lecturas con contexto y un salto extra en escrituras; tolerables, pero coste real.
- **Lo único que aporta** es **semántica**: (a) licencia **por edición** (6.036 obras CPDL con
  licencias distintas entre ediciones) y (b) **editor por edición** (`representation_persons`,
  80.166), más el agrupamiento de los ficheros de una edición.

### Opciones

1. **Disolver** `representations`: `origin`/`origin_id`/`license` a `works_resources` (o a `works`,
   que ya tiene `works_origin`/`works_origin_id`/`works_license`) y editores en una junction por
   `(origin, origin_id)`. Ahorra ~55–85 MB hoy y ~250 MB con RISM; pierde el FK y hay que agrupar
   recursos por `(origin, origin_id)` en lectura.
2. **Mantener pero reducir**: tabla solo para **CPDL ediciones** (81.983; datos reales) y recursos
   directos al work en PDMX. Elimina los 254.035 reps redundantes (~70 MB) y conserva la semántica.
3. **Mantener** tal cual: se paga ~94 MB + 18 % de join por comodidad de modelo.

La opción **2** parece el mejor equilibrio: conserva la semántica de edición donde existe y elimina
la redundancia 1:1. La **1** es la más limpia si aceptamos mover los campos y agrupar en lectura.
