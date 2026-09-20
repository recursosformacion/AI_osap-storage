# Dry-run: materializar `works_person_import` → `works_person_roles` (read-only)

Mapeo: `composer`→rol 1, `artist`→rol 10. Solo nombre único y válido.

| resultado | composer | artist |
|---|---|---|
| ya_tiene | 133356 | 74669 |
| propuesta | 1790 | 750 |
| sin_match | 11839 | 162893 |
| multiple | 0 | 132 |
| nombre_invalido | 387 | 188 |

## Muestras

| work_id | nombre | rol import → destino | persona |
|---|---|---|---|
| 232 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 337 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 372 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 395 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 414 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 418 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 445 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 483 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 598 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 646 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 693 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 946 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 958 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 1113 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 1195 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 1600 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 1752 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 1871 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 1991 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 2287 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 2292 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 2376 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 2841 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 2932 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 2983 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 3040 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 3091 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 3148 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 3508 | Trad. | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
| 4187 | Trad | composer→1 | c586d22d-5026-4ed9-876c-ad6f9045405b |
