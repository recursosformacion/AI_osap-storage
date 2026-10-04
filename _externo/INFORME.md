# Auditoria de `ensembles` -> IDs Canonicos

Trabajo realizado **solo** dentro de `_externo/`. La base de datos `osap-storage`
se abrio en modo **solo lectura**: el unico `execute` del script es un `SELECT`
sobre `ensembles` y la conexion se cierra con `rollback()` (`autocommit=False`).
No se ha insertado, actualizado ni borrado ninguna fila.

## Ficheros

| fichero | contenido |
|---|---|
| `resultado.md` | entregable: tabla Markdown de 3 columnas, 1374 filas (100% de la tabla) |
| `auditoria_detalle.csv` | traza de auditoria por fila (conteos, firma, familia, reglas aplicadas) |
| `audit_ensembles.py` | pipeline completo de canonicalizacion + consultas (SELECT) |
| `verify.py` | verificacion independiente del entregable contra la BD |
| `review.py` | utilidades de revision (notas, muestra, codigos largos,etc.) |

Ejecucion: `python _externo/audit_ensembles.py` y despues `python _externo/verify.py`.

## Resultado

- 1374 registros leidos, 1374 mapeados (100%).
- 443 IDs canonicos distintos; **178 son nuevos** (no figuran como `ensembles_code`).
- `Existe_en_Tabla = 1` en 999 filas y `0` en 375 (129 de ellas por `INVALID_OR_INSTRUMENTAL`).
- 129 codigos marcados `INVALID_OR_INSTRUMENTAL` (129 filas distintas = 9,4% del catalogo).

| familia (voz dominante) | filas |
|---|---|
| MIXED (S y B presentes) | 785 |
| MALE (T y/o B sin S) | 254 |
| FEMALE (S sin B) | 128 |
| INNER / TENOR / COUNTERTENOR / con C | 78 |
| INVALID_OR_INSTRUMENTAL | 129 |

## Formato del ID_Canonico

El enunciado admite dos formas: la firma por frecuencias (`A2T2B2`) o una
etiqueta de familia (`SATB_DOUBLE_8V`, `TTBB_MALE`). Se ha elegido la
**firma canonica en convencion propia de la base de datos**: la secuencia de
letras de voz ordenadas `S -> A -> T -> B -> C`, una letra por voz
(`AATTBB`, `TTBB`, `SATB`, `SSATB`, `SSCTTB`...).

Motivo: es la unica forma que hace util el paso 4 de verificacion. La forma
`A2T2B2` no puede coincidir con ningun `ensembles_code` (la tabla no contiene
digitos), por lo que `Existe_en_Tabla` seria 0 en las 1374 filas; con la firma
en letras, 999 filas resuelven a un ID que ya existe y las 178 restantes
identifican de forma efectiva las combinaciones derivadas que faltan en el catalogo.
Las dos formas equivalentes se conservan en `auditoria_detalle.csv`
(columnas `firma_frecuencias` = `S2A2T2B2` y `etiqueta_familia` = `SATB_MIXED_4V`,
`TTBB_MALE_4V`...).

## Reglas aplicadas

1. **Limpieza**: mayusculas, eliminacion de caracteres de control, sustitucion de
   guiones/comillas tipograficas, plegado de diacriticos (`TÉNOR` -> `TENOR`,
   `GLÄUBIGE` -> `GLAUBIGE`), colapso de espacios.
2. **Modificadores de ejecucion ignorados**: `SOLO(S)`, `SOLI`, `SOLOIST(S)`,
   `VERSE(S)`, `CHOIR(S)`, `CHORUS`, `CHORAL`, `DIVISI(S)`, `UNISON`,
   `DUET/DUO/TRIO/QUARTET`, `RIPIENI`, `DESCANT(S)`, `A CAPPELLA`
   (`A_CAPP` deja el codigo sin voces), `SEMI-CHORUS`, etc.
3. **Notacion de voces**: `BARITONE/BARITON/BARITONO/BARYTON/BARB/BAR/BRB -> B`
   (tambien en notacion pegada: `SATBARB`, `ATBARBARBARBB`, `AATTBRB`);
   `MEZZO/MEZZO-SOPRANO/MZ/MEZ -> A`; `SOPRANO/SOP -> S`, `ALTO -> A`,
   `TENOR -> T`, `BASS/BASSES -> B`; `CONTRA(LTO)/COUNTERTENOR/CT -> C`.
   `CT` se lee como dos voces (`C` + `T`), coherente con la convencion de la
   tabla, donde cada letra es una voz (`CTTBB`, `CTCTTB`...).
4. **Letras sueltas** (`S`, `A`, `T`, `B`, `C` aisladas) solo se aceptan como voz
   con contexto: otra secuencia de voces, un calificador (`SOLO`, `VERSE`...),
   un conector (`AND`, `OR`, `+`, `/`, `.`) o si el resto del codigo son solo
   palabras funcionales. Asi `B JESUS`, `A GLÄUBIGE SEELE`, `T EVANGELISTA`,
   `EACH OF S`, `WITH A FEW OCTAVES` quedan fuera, mientras que `B SOLO`,
   `B AND T`, `WITH S` si se resuelven.
5. **Multiplicadores numericos**: `2 TENORS -> TT`, `3 BASSES`, `4 SOPRANOS`,
   `TWO SOLO SOPRANOS -> SS`. El numeral solo multiplica a una voz escrita
   con palabras, nunca a una secuencia de letras.
6. **Agregacion**: los grupos separados por `.`, `/`, `+`, ` & `, espacios o
   frase (`SATB.SATB`, `SATB CHOIR AND SATB SOLOS`, `SSABAR.ATBARB.TBARBARB`)
   se suman en una sola firma, que es el ID unico exigido por el enunciado.
7. **`INVALID_OR_INSTRUMENTAL`**: pares de notas de transposicion
   (`C-A'`, `C-D`, `D'-F`, `F-G`, `B-E`, `TTBARB G-G'`), notas/ambitus sueltos
   (`C2`, `C3`, `F3`, `F4`, `C4 AND F4...`), fragmentos sin valor vocal
   (`BC`), `AD LIBITUM`, textos de roles o titulos (`I`, `M`, `V`, `MEN`,
   `WOMEN`, `CANTOR`, `AMORE`, `ANGELS`, `NARRATOR`, `LEADSHEET`,
   `SEE EDITION NOTES`), notacion instrumental (`TROMBONE 2`, `BRASS`,
   `FOR FEMALE VOICE AND PERCUSSION`) y codigos sin ninguna voz identificable
   (`UNISON`, `DUET`, `SOLO`, `TREBLE SOLO`, `SOLOSVV`, `WWMM`,
   `DISCSEPTASEXTTQUINB`, `S M C T BR`...).

## Decisiones discutibles (documentadas para revision)

- `SATBAR`/`SATBARB` se reducen a `SATB` porque `BARB` es sinonimo de baritono
  segun el enunciado (ejemplo `AATTBARBB -> A2T2B2`). La lectura musical
  alternativa (`SATBAR` = `SATB`, `SATBARB` = `SATBB`) daria 1 voz mas de bajo.
- `MEZZO SOPRANO` / `MEZZO-SOPRANO` se tratan como **una** voz (`A`), no como
  `A`+`S`, porque el enunciado equipara `MEZZO` al alto.
- `CT` se interpreta como contratenor **y** tenor (dos letras = dos voces).
- `CONTRALTO`/`CONTRA`/`COUNTERTENOR` se asignan a la categoria `C` (la quinta
  del orden canonico); `MEDIUS` se asigna a `A`.
- `DDATB` y `CAQATB` conservan solo el grupo inequivoco (`ATB`) y se marcan
  `REGLA_CURADA` en la traza; `CT2 ARE SOPRANIST AND ALTO` se interpreta como
  2 contratenores + sopranista + alto (`SACC`) segun su propia glosa.
- `TRIPLEXMEDIUSCTTB` queda en `INVALID_OR_INSTRUMENTAL` (notacion latina
  `Triplex medius` sin resolver) y requiere revision manual.
- `BRASS` se resuelve como `B` (lectura `bassus`/`basses`); puede ser
  instrumental segun el uso de la fuente.
- `DUET/DUO/TRIO` no multiplican voces (`SOPRANO DUET -> S`), porque el
  enunciado los lista como modificadores de ejecucion a ignorar.
