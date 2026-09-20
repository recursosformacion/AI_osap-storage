# Cobertura del índice RISM de personas

Generado por `scripts/analyze_rism_coverage.py` (read-only). Fuente RISM: CC-BY-3.0.

- Personas RISM indexadas: **157687** (compositores: **47856**)
- Formas de nombre indexadas: **313767**

## 1. Nuestras personas con compositor → RISM

- Personas nuestras con rol 1: **31763**
| Resultado | Personas |
|---|---|
| unico_composer | 3447 |
| unico_no_composer | 378 |
| multiple | 335 |
| sin_match | 27603 |

### Ejemplos


**unico_composer**

- Fr Chopin -> people/51160
- Pietro Mascagni -> people/84056
- Ernesto Lecuona -> people/30073487
- Thomas Tallis -> people/30004082
- Philippe Verdelot -> people/30013948
- Michael Praetorius -> people/477425
- Michael Haller -> people/41588
- William Howard Doane -> people/30106155
- Piero Benedetti -> people/40000258
- W. C. Handy -> people/30073234
- Chico Buarque -> people/30071133
- Claude Debussy -> people/4338

**multiple**

- JOHANN STRAUSS -> 4 candidatos
- William Marshall -> 2 candidatos
- Thomas Moore -> 2 candidatos
- Franz Schubert -> 5 candidatos
- Nicola Matteis -> 2 candidatos
- Renaud -> 5 candidatos
- Matteo Carcassi -> 2 candidatos
- Gabriel Marie -> 2 candidatos
- John Bishop -> 3 candidatos
- Alessandro Striggio -> 2 candidatos
- William Jones -> 2 candidatos
- Carl Czerny -> 2 candidatos

**sin_match**

- Nicki Minaj
- Cœur de pirate
- Quadrille
- Eugene Monroe Bartlett
- 林子祥
- Léon Delafosse
- Hyacinthe Klosé
- Alan Silvestri
- Alexander Goedicke
- Dominique Picard
- Luiz Gonzaga
- George Botsford

## 2. Obras sin compositor → recuperación vía RISM

- Obras sin compositor: **177024**
- Con candidato (título/hermana) y match **único** en RISM: **8200** (de las cuales el match es compositor RISM: 7148)
- Con candidato pero **sin** match RISM: 25124
- Con candidato y match **múltiple** (ambiguo): 1550

### Ejemplos de recuperación

- Allegro (id 14) -> people/30009617 [composer]
- the Crusaders (id 25) -> people/30005525 [composer]
- Come Thou fount of every blessing (id 28) -> people/30004115 [composer]
- Lady Maxwell's Reel (id 47) -> people/30007855 [composer]
- Victoria Christe resurgenti - François Couperin (id 84) -> people/30000757 [composer]
- True and loyal to our Lord above - C. Harold Lowden (id 157) -> people/30113359 [composer]
- There Is Joy In My Soul - Fanny Crosby (id 215) -> people/30106285 [no]
- Now the Savior invites you to come - Fanny J. Crosby (id 221) -> people/30106285 [no]
- Whom should we love like thee - John Bacchus Dykes (id 254) -> people/30106109 [composer]
- The Blackbird (id 398) -> people/30006887 [composer]
- St. Luke - John Heywood (id 422) -> people/30022247 [composer]
- All for Jesus! All for Jesus (Knapp) - Phoebe Palmer Knapp (id 469) -> people/30101506 [composer]
