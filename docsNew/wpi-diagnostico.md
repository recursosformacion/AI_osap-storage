# Diagnóstico `works_person_import` ↔ `persons` (read-only)

- Obras con rol 1/10 en `works_person_roles`: **156918**

## Distribución (combinaciones nombre/rol/source/resolved)


### rol `composer`

| resolved | únicos | múltiples | sin match |
|---|---|---|---|
| 1 | 25175 | 1489 | 15428 |
| 2 | 4 | 0 | 574 |

### rol `artist`

| resolved | únicos | múltiples | sin match |
|---|---|---|---|
| 0 | 7 | 0 | 262 |
| 1 | 15009 | 1333 | 1846 |
| 2 | 110 | 0 | 1932 |

## Filas por rol/resolved

| clave | filas |
|---|---|
| filas:artist:0 | 547 |
| filas:artist:1 | 77766 |
| filas:artist:2 | 160319 |
| filas:composer:1 | 145387 |
| filas:composer:2 | 1985 |

## Muestra

| nombre | rol | resolved | obras | match | persona |
|---|---|---|---|---|---|
| Misc tunes | artist | 2 | 142879 | sin_match | — |
| Misc Traditional | artist | 2 | 10511 | sin_match | — |
| anon. | composer | 1 | 4275 | sin_match | — |
| Anonymous | artist | 1 | 2278 | sin_match | — |
| Anonymous | composer | 1 | 1892 | sin_match | — |
| Johann Sebastian Bach | artist | 1 | 1442 | multiple | — |
| William Marshall | artist | 1 | 1205 | unico | 079993e3-87ec-5db4-b874-e7941311c898 |
| William Marshall | composer | 1 | 1186 | unico | 079993e3-87ec-5db4-b874-e7941311c898 |
| Trad. | composer | 1 | 1124 | unico | c586d22d-5026-4ed9-876c-ad6f9045405b |
| Orlando di Lasso | composer | 1 | 1116 | unico | 135f6c09-d533-46be-a230-219eef2aa79c |
| yoheikatowwc | artist | 2 | 980 | sin_match | — |
| Traditional | composer | 1 | 967 | sin_match | — |
| Yohei Kato åè æå¹³ | composer | 1 | 966 | unico | 04c0f383-84fd-45c3-a0b5-2f072a844620 |
| Traditional | composer | 1 | 921 | sin_match | — |
| Trad | composer | 1 | 894 | unico | c586d22d-5026-4ed9-876c-ad6f9045405b |
| Composer | composer | 2 | 676 | sin_match | — |
| William J. Kirkpatrick | artist | 1 | 635 | unico | 02421589-7a11-5194-ad89-ffd8a3a651e4 |
| Giovanni Pierluigi da Palestrina | composer | 1 | 629 | unico | 06c76167-1dd2-4d02-afa3-fc17b55f2f4e |
| Tradicional | composer | 1 | 629 | sin_match | — |
| Chas. H. Gabriel | artist | 1 | 609 | unico | ea09b231-7d4e-4e3a-9cc6-6eb5f5332aa0 |
| J. S. Bach | composer | 1 | 560 | multiple | — |
| John R. Sweney | artist | 1 | 534 | unico | 9b0847c7-4168-402d-b842-117567d0c1a0 |
| Heinrich Schütz | composer | 1 | 497 | unico | bde7f495-a9e2-4ad6-8caa-aae62f51e3a4 |
| Luca Marenzio | composer | 1 | 469 | unico | 2ac0b5e3-b4dd-4261-9ac0-c5f622ab08da |
| Heinrich Schütz | artist | 1 | 446 | unico | bde7f495-a9e2-4ad6-8caa-aae62f51e3a4 |
| Misc Computer Games | artist | 2 | 430 | sin_match | — |
| Misc Christmas | artist | 2 | 425 | sin_match | — |
| Joseph Barnby | artist | 1 | 415 | unico | 3e9def9e-1c37-49bf-88ad-8d3a27bef0eb |
| Wolfgang Amadeus Mozart | artist | 1 | 403 | multiple | — |
| Jacob Handl | composer | 1 | 384 | unico | 3aaff68e-f399-407d-af2b-e7cc74fd350e |
| Ludwig van Beethoven | artist | 1 | 377 | unico | e8994f5a-f1de-4676-bb00-7c2c8af2b2df |
| Robert Lowry | artist | 1 | 374 | unico | 98c31a83-cae1-5569-b711-9098d726b814 |
| J. Lincoln Hall | artist | 1 | 354 | unico | 8e14988b-2b4f-51ad-b489-39d6197da114 |
| Philippe de Monte | composer | 1 | 349 | unico | 49e7ccc9-6a30-4b9c-9e55-1698e95dbc90 |
| Carlotta Ferrari | composer | 1 | 346 | unico | 0b3a7b2f-3aab-42ab-bbaf-c1024060c90f |
| Alexander Walker | artist | 1 | 343 | unico | fc52bbe8-6918-4f04-8885-c32b4bd5ba44 |
| Alexander Walker | composer | 1 | 343 | unico | fc52bbe8-6918-4f04-8885-c32b4bd5ba44 |
| Claudio Monteverdi | composer | 1 | 342 | unico | 1db7cd41-45b5-40b2-973e-26c1b882b865 |
| Johann Sebastian Bach | composer | 1 | 332 | multiple | — |
| Isaac Watts | artist | 1 | 328 | unico | a16e1d40-09f7-4694-9010-7eed3b40bae0 |
