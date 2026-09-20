# Análisis de identidad de compositor y compositor ausente

Generado por `scripts/analyze_composer_identity.py` (read-only). No modifica el motor.

## Contexto

- Obras totales: **310455**
- Con compositor resuelto (rol 1): **133431** (42%)
- Sin compositor: **177024**
- Buckets por título normalizado con >1 obra: **40500** (obras implicadas: **143379**)

## Grupos antes / después por política

| Política | Grupos después | Mergers (obras - grupos) | Grupos vs current |
|---|---|---|---|
| current | 136269 | 7110 | +0 |
| A_strict | 136266 | 7113 | +3 |
| B_tolerant | 136205 | 7174 | +64 |
| P0_block | 136266 | 7113 | +3 |
| P1_catalogue | 136204 | 7175 | +65 |
| P2_sin_placeholders | 136212 | 7167 | +57 |

## Motivos y bloqueos (pares)

| Métrica | Pares |
|---|---|
| current_compositor_inequivoco | 11858 |
| B_nuevos_por_alias | 293 |
| P1_nuevos_por_catalogo | 1 |
| P2_nuevos_por_catalogo | 1 |
| composer_distinto | 137986 |
| composer_absent | 387467 |
| catalogue_conflict | 5 |

## Análisis 1 — compositor presente (pares): current vs A vs B

| Política | Pares fusionados |
|---|---|
| pares con ambos compositores presentes | 150142 |
| current | 11858 |
| A_strict | 11861 |
| B_tolerant | 12151 |

## Análisis 2 — compositor ausente (pares): P0 vs P1 vs P2

| Política | Pares fusionados |
|---|---|
| pares con compositor ausente | 387467 |
| P0_block | 0 |
| P1_catalogue | 1 |
| P2_sin_placeholders | 1 |

## Muestra de mergers nuevos (merge bajo la política, no bajo current)


### B_tolerant — 12 ejemplos

| título | work_a | work_b | compositor_a | compositor_b | id | cat_a | cat_b |
|---|---|---|---|---|---|---|---|
| Gavotte | 21066 | 148668 | J S Bach | Johann Sebastian Bach | alias_variant | None | None |
| Hjemmet er bedst | 1447 | 270916 | F A Reissiger | Friedrich August Reissiger | alias_variant | None | None |
| Sarabande de Haendel | 1458 | 29695 | G F HAENDEL | George Frideric Handel | alias_variant | None | None |
| the Cameron Highlanders | 2893 | 54617 | J Scott Skinner | J S Skinner | alias_variant | None | None |
| the Cameron Highlanders | 2893 | 138846 | J Scott Skinner | J S Skinner | alias_variant | None | None |
| the Cameron Highlanders | 2893 | 174308 | J Scott Skinner | J S Skinner | alias_variant | None | None |
| the Cameron Highlanders | 2893 | 215257 | J Scott Skinner | J S Skinner | alias_variant | None | None |
| the Cameron Highlanders | 2893 | 233220 | J Scott Skinner | J S Skinner | alias_variant | None | None |
| the Cameron Highlanders | 2893 | 245912 | J Scott Skinner | J S Skinner | alias_variant | None | None |
| the Cameron Highlanders | 50573 | 54617 | J Scott Skinner | J S Skinner | alias_variant | None | None |
| the Cameron Highlanders | 50573 | 138846 | J Scott Skinner | J S Skinner | alias_variant | None | None |
| the Cameron Highlanders | 50573 | 174308 | J Scott Skinner | J S Skinner | alias_variant | None | None |

### P1_catalogue — 1 ejemplos

| título | work_a | work_b | compositor_a | compositor_b | id | cat_a | cat_b |
|---|---|---|---|---|---|---|---|
| Now Blessed be Thou, Christ Jesu | 268425 | 284771 | None | None | missing_both | BWV 314 | BWV 314 |

### P2_sin_placeholders — 1 ejemplos

| título | work_a | work_b | compositor_a | compositor_b | id | cat_a | cat_b |
|---|---|---|---|---|---|---|---|
| Now Blessed be Thou, Christ Jesu | 268425 | 284771 | None | None | missing_both | BWV 314 | BWV 314 |

## Muestra `candidate_pair` (decisiones por política)

| título | work_a | work_b | comp_a | comp_b | identidad | cat_a | cat_b | current | A | B | P1 | P2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Allegro | 102707 | 137253 | Fran ccois Devienne | Alexander Reinagle | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Allegro | 102707 | 141937 | Fran ccois Devienne | Mauro Giuliani (1781-1828) | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Allegro | 137253 | 141937 | Alexander Reinagle | Mauro Giuliani (1781-1828) | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Allegro | 137253 | 174765 | Alexander Reinagle | Fran ccois Devienne | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Allegro | 141937 | 174765 | Mauro Giuliani (1781-1828) | Fran ccois Devienne | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 60944 | 181250 | Words Robert Robinson Nettleton | Lyrics Robert Robinson Tune of John Wyeth | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 60944 | 223877 | Words Robert Robinson Nettleton | Caden Hise | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 60944 | 259346 | Words Robert Robinson Nettleton | Thurlow Weed | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 60944 | 259424 | Words Robert Robinson Nettleton | William Boyce | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 169899 | 181250 | Words Robert Robinson Nettleton | Lyrics Robert Robinson Tune of John Wyeth | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 169899 | 223877 | Words Robert Robinson Nettleton | Caden Hise | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 169899 | 259346 | Words Robert Robinson Nettleton | Thurlow Weed | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 169899 | 259424 | Words Robert Robinson Nettleton | William Boyce | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount (of Every Blessing) | 181250 | 223877 | Lyrics Robert Robinson Tune of John Wyeth | Caden Hise | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount (of Every Blessing) | 181250 | 259346 | Lyrics Robert Robinson Tune of John Wyeth | Thurlow Weed | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount (of Every Blessing) | 181250 | 259424 | Lyrics Robert Robinson Tune of John Wyeth | William Boyce | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 223877 | 259346 | Caden Hise | Thurlow Weed | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come Thou Fount of Every Blessing | 223877 | 259424 | Caden Hise | William Boyce | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Come, Thou fount of every blessing | 259346 | 259424 | Thurlow Weed | William Boyce | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Flow gently sweet Afton | 122 | 267607 | Comp Alexander Hume | Jonathan Edwards Spilman | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Such as in God the Lord do trust - Giles Farnaby | 132 | 221049 | Psalm - Farnaby | Giles Farnaby | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 1594 | James P. Carell David S. Clayton | arr. Edwin O. Excell (1851-1921) alt.alt/tenor stem:T Boelee | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 9644 | James P. Carell David S. Clayton | Nicholas Hoover | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 18784 | James P. Carell David S. Clayton | Arr. Andrew Fowler | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 21522 | James P. Carell David S. Clayton | Music by John Newton | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 29421 | James P. Carell David S. Clayton | Words John Newton | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 75062 | James P. Carell David S. Clayton | Wayne Naus | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 91405 | James P. Carell David S. Clayton | Hymn | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 116408 | James P. Carell David S. Clayton | John Newton | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 119071 | James P. Carell David S. Clayton | John Newton | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 125053 | James P. Carell David S. Clayton | Appalacian Folk Melody | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 146871 | James P. Carell David S. Clayton | Arranged by: KingFredrick_VI | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 175905 | James P. Carell David S. Clayton | John Newtonarr E Muirhead | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 177332 | James P. Carell David S. Clayton | Marissa Hoisington | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 186679 | James P. Carell David S. Clayton | Retarra | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 189512 | James P. Carell David S. Clayton | arr. Vince Lewis | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 200110 | James P. Carell David S. Clayton | Original Song by John Newton | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 224666 | James P. Carell David S. Clayton | Musique: William WalkerParoles: Jonh NewtonArrangement: Louis-Félix Robitaille | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 229086 | James P. Carell David S. Clayton | Filip BlaškoviÄ | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
| Amazing Grace | 164 | 233127 | James P. Carell David S. Clayton | Words John Newton | different | None | None | no_union | no_union | no_union | no_union | no_union | no_union |
