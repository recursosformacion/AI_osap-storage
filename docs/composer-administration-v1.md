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

### `GET /api/admin/composers?q=&limit=&offset=`

Listado paginado de compositores **activos**.

- `q`: filtra por nombre o alias usando la misma normalización del resolver.
- `limit` (1-500, por defecto 50), `offset` (por defecto 0).

```json
{
  "items": [
    {
      "id": "8f5b3a7e-...",
      "name": "Wolfgang Amadeus Mozart",
      "status": "active",
      "aliases_count": 5,
      "works_count": 264
    }
  ],
  "total": 1
}
```

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
osap-storage populate-composers <csv>
osap-storage backfill-composer-ids          # rellena works.composer_id desde works.composer
```
