# Fase 2A — Fuentes RISM: conexión obra↔persona y contrato de evidencia

Generado por `scripts/analyze_rism_sources.py` (read-only). Fuente RISM: CC-BY-3.0.

- Fuentes RISM leídas: **1565667**
- Obras con candidato y match de persona RISM: **9709**
- Personas RISM objetivo: **1931**

## Contrato de evidencia (`100 $j` → estado del resolver)

| `$j` | Estado | ¿Resuelve compositor? |
|---|---|---|
| Verified | resolved | sí |
| Ascertained | inferred | sí |
| Conjectural | ambiguous | no automáticamente |
| Alleged | ambiguous | no automáticamente |
| Doubtful | ambiguous | no automáticamente |
| (sin $j) | unclassified | no automáticamente |
| solo_nominal | unclassified | no automáticamente |

`resolved` = evidencia externa suficientemente fuerte para que el resolver la considere
atribución resuelta; no significa que «RISM diga la verdad».

## Matching endurecido (2A.1)

Conexión fuerte = título uniforme `240` **o** ≥2 tokens significativos coincidentes (+ persona).
Se excluyen títulos de un solo token significativo y tokens genéricos (Gavotte, Air, Mass…).

## Clasificación

| Resultado | Obras |
|---|---|
| solo_nominal | 4329 |
| conecta_fuerte | 2476 |
| solo_nominal_debil | 1702 |
| sin_fuentes_rism | 1202 |

Conexiones fuertes por vía: 240=824, 245=1652

## Estado de evidencia de las conexiones fuertes

| Estado | Obras |
|---|---|
| unclassified | 1320 |
| inferred | 868 |
| resolved | 234 |
| ambiguous | 54 |

## Fiabilidad (`$j`) de las conexiones fuertes

| `$j` | Obras |
|---|---|
| (sin $j) | 1320 |
| Ascertained | 868 |
| Verified | 234 |
| Conjectural | 43 |
| Alleged | 10 |
| Doubtful | 1 |

## Ejemplos


**conecta_fuerte**

- Victoria Christe resurgenti - François Couperin (id 84) vía 240 [sin $j]
- Lebenslust - Franz Schubert (id 97) vía 245 [sin $j]
- Grazie a gl'inganni tuoi K. 532 - Wolfgang Amadeus Mozart (id 467) vía 245 [sin $j]
- Tulerunt Dominum meum - Gregor Lange (id 512) vía 240 [Ascertained]
- Charlie is my Darling (id 925) vía 240 [sin $j]
- Dreadful Pride Chastising Word - Charles Wesley (id 1111) vía 245 [sin $j]
- Ich will den Herren loben allezeit SWV 306 - Heinrich Schütz (id 1182) vía 245 [Ascertained]
- The Lass of Richmond Hill (id 1200) vía 240 [sin $j]
- Magnificat a 8 - Giovanni Gabrieli (id 1262) vía 245 [sin $j]
- Lobe den Herren (id 1299) vía 245 [sin $j]
- Veni creator - H. Battre (id 1334) vía 240 [sin $j]
- Ye spotted snakes - Richard John Samuel Stevens (id 1428) vía 240 [Ascertained]

**solo_nominal_debil**

- Come Thou fount of every blessing (id 28)
- Whom should we love like thee - John Bacchus Dykes (id 254)
- The Blackbird (id 398)
- All for Jesus! All for Jesus (Knapp) - Phoebe Palmer Knapp (id 469)
- Ut re mi fa sol la (id 478)
- Planxty George Brabazon (id 609)
- The snow was drifting over the hill (Williams) - W. A. Williams (id 754)
- Shalem - Lowell Mason (id 1409)

**solo_nominal**

- Allegro (id 14)
- the Crusaders (id 25)
- Lady Maxwell's Reel (id 47)
- True and loyal to our Lord above - C. Harold Lowden (id 157)
- St. Luke - John Heywood (id 422)
- Today the saints in Zion are watching - Geo. C. Stebbins (id 544)
- There will dawn a golden morrow by and by - J. H. Fillmore (id 685)
- We have heard the story - James McGranahan (id 700)

**anonimo_rism**

(sin ejemplos)
