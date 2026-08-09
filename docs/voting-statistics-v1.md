# Voting & Statistics v1

Sistema de votación y estadísticas de obras y compositores en **osap-storage**.

Storage es el propietario de los datos persistentes de obras, compositores, **votos** y
**estadísticas**. El cálculo estadístico y el proceso nocturno pertenecen a Storage; osap-api no
calcula estadísticas ni medias. Storage no introduce lógica de osap-api, Work Resolution ni
Matching.

---

## Modelo de datos

### `votes` (datos fuente)

| campo     | tipo              | descripción                                      |
|-----------|-------------------|--------------------------------------------------|
| `id`      | BIGINT (PK)       |                                                  |
| `user_id` | `VARCHAR`         | Identificador del usuario.                       |
| `work_id` | BIGINT (FK works) | Obra votada.                                     |
| `vote`    | `TINYINT`         | Valoración `1..5` (con `CHECK`).                 |
| `voted_at`| `DATETIME`        | Cuándo se votó.                                  |
| `vote_day`| `DATE`            | Día en **UTC**.                                  |

Restricción: `UNIQUE(user_id, work_id, vote_day)` — un usuario puede votar **una vez al día por
obra**; puede votar obras distintas el mismo día. La unicidad se garantiza en la **base de datos**
(no solo en Python), por lo que es segura ante peticiones concurrentes.

### `work_statistics` (datos derivados)

| campo             | tipo             | descripción                            |
|-------------------|------------------|----------------------------------------|
| `work_id`         | BIGINT (PK/FK)   | Obra.                                  |
| `rating`          | `DECIMAL(10,3)`  | Media de sus votos (o `NULL`).         |
| `adjusted_rating` | `DECIMAL(10,3)`  | Media suavizada hacia la global.       |
| `vote_count`      | `INT`            | Número de votos.                       |
| `work_count`      | `INT`            | `1`.                                   |
| `confidence`      | `DECIMAL(5,4)`   | `min(1, vote_count / m)`.              |
| `calculated_at`   | `DATETIME`       | Fecha/hora del último cálculo.         |

Solo existen filas para obras **con votos**. Si una obra no tiene votos, el endpoint devuelve
`vote_count = 0` y `rating = null` sin inventar datos.

### `composer_statistics` (datos derivados)

| campo             | tipo              | descripción                            |
|-------------------|-------------------|----------------------------------------|
| `composer_id`     | `CHAR(36)` (PK/FK)| Composer canónico activo.              |
| `rating`          | `DECIMAL(10,3)`   | Media ponderada de sus Works.          |
| `adjusted_rating` | `DECIMAL(10,3)`   | Igual que `rating` (agregado ya suavizado).|
| `vote_count`      | `INT`             | Votos agregados de sus Works.          |
| `work_count`      | `INT`             | Works con `composer_id` = este.        |
| `confidence`      | `DECIMAL(5,4)`    | `min(1, vote_count / m)`.              |
| `calculated_at`   | `DATETIME`        | Fecha/hora del último cálculo.         |

Los compositores **fusionados** (`status = merged`) no reciben estadística independiente: el
recálculo las elimina y solo agrega para compositores **activos**.

### `statistics_runs`

Registro de cada ejecución del proceso de recálculo: `started_at`, `finished_at`,
`works_updated`, `composers_updated`.

---

## Fórmulas (congeladas v1)

Parámetros: `m = 5` (mínimo de votos para confianza plena) y `global_mean = AVG(vote)` global
(media de todos los votos). Escala de voto: `1..5`.

**Rating de Work** = `AVG(vote)` de sus votos.

**Adjusted rating de Work** = media suavizada hacia la media global (prior bayesiano):

```
adjusted = (vote_count * rating + m * global_mean) / (vote_count + m)
```

Con pocos votos se aproxima a `global_mean`; con muchos, a `rating`. Evita resultados absurdos
con pocos votos, por lo que no hace falta un algoritmo especial para compositores con pocas obras.

**Confidence** = `min(1, vote_count / m)`.

**Peso de Work para Composer** = `sqrt(vote_count)`.

**Rating de Composer** = media ponderada de los `adjusted_rating` de sus Works, ponderada por
`sqrt(vote_count)`:

```
composer_rating = Σ(adjusted_i * sqrt(vote_count_i)) / Σ(sqrt(vote_count_i))
```

**work_count** = número de Works con `composer_id` = compositor (compositor activo canónico).

Campos almacenados siempre (Work y Composer): `rating`, `adjusted_rating`, `vote_count`,
`work_count`, `confidence`, `calculated_at`.

---

## Proceso nocturno

Comando idempotente que recalcula todas las estadísticas derivadas:

```
osap-storage recompute-statistics
```

Transaccional y re-ejecutable sin duplicar datos (`INSERT ... ON DUPLICATE KEY UPDATE`). Hace:

1. Recalcula `work_statistics` para obras con votos.
2. Elimina `composer_statistics` de compositores no activos o inexistentes.
3. Recalcula `composer_statistics` agregando por compositor activo.
4. Registra una fila en `statistics_runs`.

**Ejecución programada (producción)**: un cron/systemd timer que invoca el comando
diariamente, p. ej.:

```
0 3 * * * ocw  cd /home/ocw/openmusicrepository.com/osap-storage && ./.venv/bin/python -m infrastructure.cli recompute-statistics
```

No depende de osap-api.

---

## Comportamiento ante fusiones

Los votos pertenecen a una **Work**, no directamente a un Composer. Al fusionar compositores:

- las Works se reasignan al target (`works.composer_id`);
- el siguiente recálculo produce automáticamente la valoración del compositor destino;
- la estadística del compositor `merged` se elimina (no queda como identidad independiente);
- no se duplican votos (cada voto sigue asociado a su Work).

---

## APIs

Los endpoints separan claramente datos fuente (`votes`) de datos derivados
(`work_statistics` / `composer_statistics`).

### `POST /api/v1/works/{work_id}/votes`

Body: `{ "user_id": "...", "vote": 1..5 }`

Registra el voto. `201` si es nuevo. `409` si el usuario ya votó esa obra hoy
(`DuplicateVote`). `404` si la obra no existe. `422` si el voto no está en 1..5.

```json
{ "id": 1, "user_id": "u1", "work_id": 264, "vote": 5, "voted_at": "...", "vote_day": "2026-08-09" }
```

### `GET /api/v1/works/{work_id}/statistics`

```json
{ "work_id": 264, "rating": 4.583, "adjusted_rating": 4.550, "vote_count": 12, "work_count": 1, "confidence": 1.0, "calculated_at": "..." }
```

### `GET /api/v1/composers/{composer_id}/statistics`

Devuelve la del compositor **canónico**. Si el id es un compositor fusionado, resuelve al target
activo y devuelve su estadística.

```json
{ "composer_id": "8f5b3a7e-...", "rating": 4.72, "adjusted_rating": 4.72, "vote_count": 100, "work_count": 264, "confidence": 1.0, "calculated_at": "..." }
```

---

## Notas

- No se modifican los contratos congelados de autenticación.
- El contrato público Provider API v1.3 (`/api/search`, `/api/lookup`, `/api/resource/{id}`,
  `/api/download/{resource_id}`) no cambia: la estadística de votación se expone en los endpoints
  nuevos de esta sección.
