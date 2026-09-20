# Fase 2B — Evidencia de autoridad RISM para nuestras personas

Generado por `scripts/analyze_rism_person_matches.py` (read-only). NO modifica `persons`.
Fuente RISM: CC-BY-3.0.

- Personas nuestras con rol 1 (compositor): **31763**
- Match **único** en RISM: **3825** | múltiple: 335 | sin match: 27603

## Qué aporta RISM a esos matches únicos

| Dato | Personas |
|---|---|
| con GND | 2686 |
| con VIAF | 2824 |
| con fechas | 3566 |
| RISM no lo marca «Composer» | 378 |

## Fechas

| Resultado | Personas |
|---|---|
| coincide | 629 |
| rellenable_nacimiento | 2414 |
| rellenable_muerte | 2224 |
| conflicto_nacimiento | 85 |
| conflicto_muerte | 39 |

## Nombre canónico (nuestro vs RISM)

| Resultado | Personas |
|---|---|
| concordante | 3103 |
| solo_orden | 0 |
| difiere | 722 |

## Variantes de nombre

- Personas que ganarían alias: **2670**
- Total de alias nuevos: **13622**

## Ejemplos


**alias_nuevo**

- Peter K. Moran += Moran, P. K.
- S S Wesley += Wesley, Samuel Sebastian
- S S Wesley += Wesley, Samuel S.
- Johannes Zahn += Zahn, Johann Christoph Andreas
- Johannes Zahn += Zahn, Joh.
- Johannes Zahn += Zahn, Johann
- Tommaso Bai += Baj, Tommaso
- Tommaso Bai += Baij, Tommaso
- Tommaso Bai += Bay, Tommaso
- Tommaso Bai += Bai, Thomas
- Leonhard von Call += Call zu Zulmbach, Leonhard
- Leonhard von Call += Call, Léonard de
- Leonhard von Call += Call, Leonard von
- Leonhard von Call += Call, Leonhard
- Leonhard von Call += Call, L. de

**nombre_difiere**

- S S Wesley <> Wesley, Samuel Sebastian
- Tommaso Bai <> Baj, Tommaso
- Johannes Kugelmann <> Kugelmann, Hans
- S Rachmaninoff <> Rachmaninov, Sergej Vasil'evič
- Giovanni de Antiquis <> De Antiquis, Giovanni Giacomo
- E B Smith <> Smith, Elise Becket
- Joan Baptista Lambert <> Lambert, Joan B.
- Queen Liliuokalani <> Liliuokalani, Queen of Hawaii
- James Frederick Swift <> Marks, Godfrey
- Christoph Straus <> Strauss, Christoph
- Pier Francesco Cavalli <> Cavalli, Francesco
- Leonardus Barré <> Barré, Leonardo
- François du Bois <> Du Boys, Francoys
- G Bizet <> Bizet, Georges
- Ludwig Hellwig <> Hellwig, Karl Ludwig

> Riesgo: el match es por nombre normalizado; en nombres comunes puede haber falso
> positivo. Antes de escribir en `persons`, validar con GND/VIAF/fechas y revisión.
