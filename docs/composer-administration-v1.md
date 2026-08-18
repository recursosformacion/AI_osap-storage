# Composer Administration API v1

Administración de la identidad canónica de compositores en **osap-storage**.

Storage es el propietario de:

- `composers`
- `composer_aliases`
- la relación `Work → composer_id`
- las operaciones de fusión de compositores

Estos endpoints son **administrativos** y están separados del contrato público Provider API v1.3
(`/api/search`, `/api/lookup`, `/api/resource/{id}`, `/api/download/{resource_id}`). La decisión
de qué compositores fusionar es **manual**; Storage solo proporciona información para facilitarla
y nunca ejecuta fusiones automáticas.

---

## Modelo

### `composers`

| campo        | tipo            | descripción                                             |
|--------------|-----------------|---------------------------------------------------------|
| `id`         | `CHAR(36)` (PK) | UUID estable y opaco.                                   |
| `name`       | `VARCHAR`       | Nombre canónico del compositor.                         |
| `status`     | `VARCHAR`       | `active` o `merged`.                                    |
| `merged_into`| `CHAR(36)` NULL | Id del compositor target cuando `status = merged`.      |
| `merged_at`  | `DATETIME` NULL | Cuándo se fusionó.                                      |
| `review_status`| `VARCHAR`     | `correct`, `incorrect`, `reviewed` o `not_reviewed` (clasificación heurística). |
| `reviewed_at`| `DATETIME` NULL | Cuándo se revisó.                                       |

### `composer_aliases`

| campo             | tipo           | descripción                                             |
|-------------------|----------------|---------------------------------------------------------|
| `id`              | BIGINT (PK)    |                                                         |
| `composer_id`     | `CHAR(36)` (FK)| Composer al que pertenece el alias.                     |
| `alias`           | `VARCHAR`      | Nombre original (tal cual lo entregó el proveedor).     |
| `normalized_alias`| `VARCHAR`      | Forma normalizada. `UNIQUE`: no puede apuntar a dos.    |

### `composer_merge_history`

| campo                  | tipo            | descripción                                           |
|------------------------|-----------------|-------------------------------------------------------|
| `id`                   | BIGINT (PK)     |                                                       |
| `merge_operation_id`   | `CHAR(36)` NULL | Agrupa los sources de una misma operación de merge.   |
| `source_composer_id`   | `CHAR(36)` (FK) | Composer que se fusionó.                              |
| `target_composer_id`   | `CHAR(36)` (FK) | Composer que permanece.                               |
| `merged_at`            | `DATETIME`      |                                                       |
| `merged_by`            | `VARCHAR` NULL  | Actor administrativo (punto de integración de auth).  |

`composer_merge_history` conserva la trazabilidad. Los composers `merged` no se borran
físicamente; se marcan como `merged` con `merged_into` para resolver referencias antiguas.

---

## Endpoints

Todos bajo `/api/admin/composers`.

### `GET /api/admin/composers?q=&review=&limit=&offset=`

Listado paginado de compositores **activos**.

- `q`: filtra por nombre o alias usando la misma normalización del resolver.
- `review`: filtra por estado de revisión (`correct`, `false`, `pending`).
- `limit` (1-500, por defecto 50), `offset` (por defecto 0).

```json
{
  "items": [
    {
      "id": "8f5b3a7e-...",
      "name": "Wolfgang Amadeus Mozart",
      "status": "active",
      "aliases_count": 5,
      "works_count": 264,
      "review_status": "pending"
    }
  ],
  "total": 1
}
```

### `POST /api/admin/composers/{id}/review`

Body: `{ "review_status": "correct" | "incorrect" | "reviewed" | "not_reviewed" }`

Marca el estado de revisión de un compositor (no borra ni modifica la identidad). El listado
permite filtrar por `?review=` para revisar solo los `incorrect` (sospechosos) o los
`not_reviewed`.

### Clasificación heurística y extracción (NER)

`osap-storage classify-composers` aplica una heurística (`domain/services/composer_quality.py`)
sobre los compositores `not_reviewed`:

- `correct`: nombre limpio de persona.
- `incorrect`: sospechoso claro (patrones como `arranged from/by`, `attributed to`, `arr.`,
  `by `, `[]`, `&`, `/`, cifras, sin letras). Estos van a la lista de revisión manual.
- `not_reviewed`: ambiguo (palabra única o caracteres no sencillos), sin veredicto.
- `reviewed`: lo fija la administración; el clasificador no lo emite.

La extracción del compositor dentro del texto bruto usa dos fases (aplicadas en `populate-composers`
y en el enlace de obras, para que ambos coincidan):

1. **Heurística por marcas** (`arranged by/from`, `attributed to`, `arr.`, `" by "`) → compositor
   claro antes/después de la marca.
2. **NER** (spaCy `en_core_web_md`, opcional): extrae la entidad `PERSON` más larga, p. ej.
   `"A bluegrass song gone haywire David Ladue"` → `"David Ladue"`.

El candidato resultante pasa por `validar_nombre_compositor` (puntuación antroponímica: iniciales,
mayúsculas, partículas, palabras prohibidas como `song`/`bluegrass`/`op`...). Si no es válido, el
nombre se descarta y la obra va a "Compositor sin indicar". Dependencia opcional: `pip install
"spacy>=3.7"` + `python -m spacy download en_core_web_md`.

Es un filtro agresivo y no garantiza la identidad canónica; la revisión final es manual.

---

## Catálogos musicales

Los **catálogos temáticos** (Köchel, BWV, Hoboken, Ryom, Deutsch, Zimmerman...) identifican el
catálogo de una obra por su **prefijo/sigla** y señalan al **compositor**, por lo que participan en
el registro de obras y ayudan a la **limpieza de compositores**.

### Modelo — `catalogues`

| campo                | tipo        | descripción                     |
|----------------------|-------------|---------------------------------|
| `prefix`             | `VARCHAR`   | Sigla (K, KV, BWV, Hob, RV, D...).|
| `composer`           | `VARCHAR`   | Compositor del catálogo.        |
| `catalogue_name`     | `VARCHAR`   | Nombre del catálogo.            |
| `creator`            | `VARCHAR`   | Creador / musicólogo.           |
| `ordering_criterion` | `VARCHAR`   | Criterio de ordenación.         |

Se siembra de forma idempotente con `osap-storage seed-catalogues`.

### API

`GET /api/v1/catalogues` (protegida por service token `storage:read`):

- `?prefix=K` → catálogos con sigla K (Mozart, Scarlatti...).
- `?composer=mozart` → catálogos de ese compositor.
- sin filtros → listado paginado (`limit`, `offset`).

### Integración con la limpieza

`CatalogueQueries.composer_from_reference(ref)` extrae el prefijo de una referencia de obra
(p. ej. `"BWV 846"` → `BWV`, `"K. 15h"` → `K`) y, si el prefijo identifica a **un único**
catálogo, devuelve su compositor (p. ej. BWV → Johann Sebastian Bach). Si es ambiguo (p. ej. K
→ Mozart y Scarlatti), devuelve `None`.

El enlace de obras (`backfill-composer-ids`) lo usa como **fallback**: si no se puede extraer el
compositor del texto de la obra pero su catálogo es inequívoco, se asigna el compositor del
catálogo. Esto reduce las obras que quedan en "Compositor sin indicar" por falta de pista.

---

## CRUD genérico de tablas (para osap-api)

Existe un CRUD genérico sobre las tablas de osap-storage, **protegido** y pensado para que lo
consuma **exclusivamente osap-api** (con service token `storage:admin`). Vive bajo
`/api/admin/tables`:

- `GET /api/admin/tables` → lista las tablas expuestas.
- `GET /api/admin/tables/{table}?limit=&offset=` → lee filas (paginado).
- `GET /api/admin/tables/{table}/{pk}` → lee una fila por clave primaria.
- `POST /api/admin/tables/{table}` → crea una fila (body: objeto con columnas).
- `PUT /api/admin/tables/{table}/{pk}` → actualiza una fila.
- `DELETE /api/admin/tables/{table}/{pk}` → borra una fila.

Seguridad:
- Requiere `storage:admin` (la auth de servicio lo protege; sin token → 401).
- La tabla debe estar en un **whitelist**; las columnas se validan contra las reales de la tabla
  (las desconocidas se ignoran); todos los valores van **parametrizados** (sin inyección SQL).
- Las tablas internas (`schema_migrations`) no se exponen.

---

## Recuperación de identidad de compositores (desde la obra)

Cuando el `composer_name` de PDMX llega corrupto (mojibake por encoding), **no se repara desde el
nombre** (no es fuente de verdad). `ComposerRecoveryService` recupera la identidad **desde la obra**
(título) y deja auditoría:

1. **`detect_suspicious`** — marca como sospechosos los compositores con nombre corrupto
   (`composers.suspicious=1`, `suspicious_reason='encoding_anomaly'`), sin cambiar el valor.
2. **`recover(work)`** — para una obra con compositor sospechoso:
   - extrae la identidad del **título**;
   - busca evidencias independientes (MusicBrainz **`work`** → compositor `Person`);
   - calcula **confianza** (coincidencia exacta de título, nombre en el título);
   - guarda un **`composer_resolution`** (auditoría: work_id, old_composer_id,
     candidate_composer_id, reason, evidence, confidence, resolver_version, decision);
   - si `confidence >= 0.9` → `auto_correct` (crea/enlaza el candidato y actualiza
     `work.composer_id`); si no → `pending_human` (revisión con la evidencia a la vista).
   - El dato original corrupto **no se destruye** (queda como `old_composer_id`/evidencia).

Comando:

```
osap-storage recover-composer-identities --limit N
```

Tablas: `composers.suspicious`/`suspicious_reason`, `composer_resolution` (auditoría).

### Resolución delegada a osap-api

Storage **no consulta entidades externas** (MusicBrainz, Wikidata, VIAF...): **osap-api** es el
especialista. Storage llama a su endpoint público

```
POST https://app.openmusicrepository.com/api/v1/composers/resolve
```

con un payload mínimo `{work:{title, catalog, year}, composer:{name}, source, representations}`,
y procesa la respuesta (`data.status`, `data.composer`, `data.confidence`, `data.input_quality`,
`data.candidates[]`, `data.evidence[]`):

- `status=resolved` → el compositor es la identidad canónica; storage la crea/enlaza
  (`work.composer_id` = candidato), guarda alias/`musicbrainz_id`, y registra la resolución.
- `status=ambiguous` → hay candidatos; revisión humana (`pending_human`).
- `status=not_found` → sin candidatos; **no inventa** (`pending_human`).
- `input_quality=corrupt_or_suspicious` → un nombre corrupto **nunca** se convierte en el canónico
  (osap-api resuelve a partir de la obra, no del nombre).

Cliente: `infrastructure/services/osap_api_client.py`. Config: `osap_api.base_url` (y opcional
`osap_api.service_token` para `Authorization: Bearer`). Comando:

```
osap-storage recover-composer-identities --limit N
```

El dato original corrupto nunca se destruye: queda como `old_composer_id`/evidencia en
`composer_resolution`.

### Pantalla web de gestión (osap-storage)

osap-storage sirve una **pantalla web completa** del CRUD en `GET /admin`. Es storage quien
realiza todas las funciones; osap-api solo necesita un enlace **"Gestión storage"** que apunte a
esa pantalla:

```
https://storage.openmusicrepository.com/admin?token=<service-token-storage:admin>
```

La página (shell) se sirve sin token (no contiene datos), pero las operaciones las realiza su JS
llamando a `/api/admin/tables/*` con el service token como `Bearer` (protegido con `storage:admin`).
Esto mantiene storage ajeno a usuarios: solo autentica el **servicio** (osap-api) que le pasa el
token.

### `GET /api/admin/composers/candidates?q=&limit=&offset=`

Asistencia a la revisión manual. Devuelve compositores activos que coinciden con la búsqueda por
nombre o alias. **Solo propone**; nunca ejecuta fusiones.

### `GET /api/admin/composers/{id}`

Detalle de un compositor (activo o merged).

```json
{
  "id": "8f5b3a7e-...",
  "name": "Wolfgang Amadeus Mozart",
  "status": "active",
  "aliases": ["W. A. Mozart", "Mozart, W. A."],
  "works_count": 264,
  "merged_into": null,
  "merged_at": null
}
```

Para un compositor `merged`, `status = "merged"` y `merged_into` apunta al target.

### `GET /api/admin/composers/{id}/works?limit=&offset=`

Works asociadas al compositor (paginado), para revisar el impacto de una fusión.

```json
{
  "items": [
    { "work_id": 264, "title": "Contredanse in F, K. 15h", "composer_id": "8f5b3a7e-..." }
  ],
  "total": 1
}
```

### `POST /api/admin/composers/{target_id}/merge`

Body:

```json
{ "source_ids": ["uuid-1", "uuid-2"] }
```

Semántica: `target_id` permanece; `source_ids` se fusionan dentro de él. Puede haber uno o varios
sources; `target` no puede aparecer entre los sources; todos deben existir.

Respuesta:

```json
{
  "target_id": "8f5b3a7e-...",
  "sources_merged": ["uuid-1", "uuid-2"],
  "aliases_transferred": 6,
  "works_moved": 14,
  "merge_operation_id": "5f9c...-"
}
```

---

## Reglas transaccionales del merge

La fusión es **atómica** (una sola transacción). Dentro de ella:

1. **Validación**: target existe y es `active`; todos los sources existen; `target` no está entre
   los sources; ningún source está ya fusionado en otro target.
2. **Aliases**: todos los alias de los sources pasan al target (sin duplicar; se respeta el
   `UNIQUE(normalized_alias)`). Si aparece un conflicto no resoluble, **aborta toda la operación**
   (no hay fusión parcial).
3. **Works**: `UPDATE works SET composer_id = :target WHERE composer_id IN (:sources)`.
4. **Estado**: cada source pasa a `status = merged` con `merged_into = :target` y `merged_at`.
5. **Historial**: un registro por source en `composer_merge_history`, agrupado por el mismo
   `merge_operation_id`.

**Idempotencia**: si se repite una fusión ya realizada (sources ya `merged` en ese target), es un
no-op que no corrompe datos. Fusionar un compositor ya fusionado en *otro* target lanza
`InvalidMerge` (400). Un source inexistente o un target inexistente lanza 404; `target` entre los
sources lanza 400.

---

## Resolución después de una fusión

El `ComposerResolver` sigue funcionando: un alias que ahora pertenece a un compositor `merged`
resuelve al compositor **activo final** (sigue `merged_into`). La resolución es por lotes y no
introduce N+1. Las Works quedan apuntando siempre al `composer_id` canónico activo.

---

## Autorización

Estos endpoints son administrativos. No se introduce un sistema de autorización nuevo en esta
versión; el punto de integración queda preparado (`merged_by` en el historial, y el prefijo
`/api/admin/`). Cuando la autenticación administrativa del servicio esté cableada, debe protegerse
esta sección; no hay una solución paralela en el código.

---

## Población de `composers` / `composer_aliases`

Ver "Población inicial" en `docs/provider-api-contract.md`. Comandos:

```
osap-storage populate-composers <csv>                 # --provider registra evidencia de creación
osap-storage backfill-composer-ids                    # rellena works.composer_id desde works.composer
osap-storage backfill-creation-evidence --provider pdmx   # evidencia para compositores activos sin ella
```

---

## Requisito — Evidencia de creación de compositores

> Estado: **implementado** (tabla `composer_creation_evidence`). Se registra al crear un
> compositor a partir de una obra y se conserva como trazabilidad.

### Motivación

Hoy un compositor se representa aproximadamente como:

```
composer
 ├── nombre
 ├── aliases
 └── works
```

Cuando un compositor se genera a partir de una obra (extracción), se pierde el **motivo por el que
nació ese registro**. Esto dificulta la decisión de fusión y oculta errores del propio algoritmo de
extracción.

### Concepto

Se introduce la noción de **evidencia de origen del compositor automático** (nombre tentativo en
el modelo definitivo: `creation_evidence`). Distinguir:

- **compositor creado manualmente** → sin evidencia automática;
- **compositor creado por extracción** → evidencia de extracción que conserva la obra que provocó
  la creación, los datos originales extraídos y el origen/proveedor.

### Datos a conservar

Cuando el algoritmo crea un compositor a partir de una obra, debe quedar asociada al menos una
referencia a la obra que originó la creación:

```
Composer
 ├── id
 ├── name
 ├── aliases
 ├── ...
 └── creation_evidence
       ├── work_id                     # referencia a la obra (propiedad de osap-storage)
       ├── nombre de la obra
       ├── datos de autor extraídos    # texto/autor extraído originalmente
       ├── proveedor / origen
       └── referencia al recurso original
```

No se copia la obra dentro del compositor: se conserva una **referencia a `work_id`**, porque la
obra ya es propiedad de osap-storage.

### Utilidades

1. **Pantalla de fusión**: mostrar por qué existe cada registro antes de fusionar.

   ```
   Compositor: Johann Sebastian Bach
   Creado automáticamente a partir de:
     Preludio en Do mayor
     proveedor: IMSLP
     referencia: ...
     autor extraído originalmente: J. S. Bach

   Compositor: J. S. Bach
   Creado a partir de:
     Prelude BWV 846
     proveedor: X
     autor extraído: Johann Seb. Bach
   ```

2. **Detección de errores de extracción**: al revisar la fuente se puede determinar si el
   compositor está bien identificado, si el nombre se normalizó mal, si se creó un duplicado, si se
   atribuyó la obra al compositor equivocado, o si el texto extraído no era realmente el
   compositor. Esto es mucho más valioso que almacenar simplemente "este compositor tiene estas
   obras".

### Regla de fusión

**No borrar la evidencia de creación tras una fusión.** La trazabilidad histórica puede ser
precisamente lo que se necesite para deshacer o investigar una atribución incorrecta. La fusión
redirige la evidencia de los compositores origen hacia el target (y registra la operación en
`composer_merge_history`), **nunca la elimina**.

### Modelo

Tabla `composer_creation_evidence`:

| campo               | tipo             | descripción                              |
|---------------------|------------------|------------------------------------------|
| `id`                | BIGINT (PK)      |                                          |
| `composer_id`       | `CHAR(36)` (FK)  | Composer al que pertenece la evidencia.  |
| `work_id`           | BIGINT NULL (FK) | Referencia a la obra que originó la creación. |
| `work_title`        | `VARCHAR`        | Nombre de la obra en el momento de creación. |
| `extracted_author`  | `VARCHAR`        | Datos de autor extraídos originalmente.  |
| `provider`          | `VARCHAR`        | Proveedor / origen.                      |
| `resource_reference`| `VARCHAR`        | Referencia al recurso original.          |
| `created_at`        | `DATETIME`       |                                          |

La obra no se copia en el compositor: se conserva una **referencia a `work_id`**. En `GET
/api/admin/composers/{id}` el detalle incluye `creation_evidence` con estos datos, de modo que la
pantalla de fusión puede mostrar por qué existe cada registro y detectar errores de extracción
(normalización mal hecha, duplicados, atribución errónea, texto que no era el compositor).

### Alcance

Este requisito aplica a osap-storage y afecta a la administración de compositores. Queda fuera
de esta anotación la lógica de osap-api.

## Gestión de alias y atribución

- `GET /api/admin/composers/{composer_id}/aliases` — lista los alias de un compositor (con id).
- `POST /api/admin/composers/{composer_id}/aliases` — añade un alias (normalizado).
- `POST /api/admin/composers/{composer_id}/aliases/{alias_id}/move` — mueve el alias a otro compositor y reasigna las obras que lo aportaron (`works.composer` = alias, `composer_id` = origen).
- `POST /api/admin/composers/{composer_id}/aliases/{alias_id}/promote` — crea un Composer desde el alias y reasigna sus obras.
- `POST /api/admin/composers/set-attribution` — convierte compositores a atribución: las obras guardan `attribution_type` + `attribution_note` (= nombre), se borra `composer_id`, y el compositor se retira (status merged, invisible, revisión incorrecta).

Reglas: los alias nunca se borran; se mueven o promueven. La fusión ya añade los orígenes como alias del destino y reasigna obras.
