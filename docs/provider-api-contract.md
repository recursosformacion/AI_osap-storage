# OSAP Provider API Contract v1.3

## Introducción

Este documento define el contrato que **osap-storage** expone como proveedor de información.

> **v1.3**: rediseño del contrato. **No** mantiene compatibilidad conceptual con versiones
> anteriores. Los cambios son **incompatibles**.

## Filosofía

**osap-storage es un proveedor de información.** Su única responsabilidad es:

- **localizar** obras,
- devolver **toda la información conocida** sobre una `Work`,
- generar los **enlaces de descarga** de los recursos físicos.

osap-storage **no conoce**:

- Matching Works
- Work Resolution
- Relationships
- Knowledge Hub
- Representations

Será **OSAP-API** quien adapte esta información a su modelo interno (RepresentationInfo, etc.).
Storage solo publica datos y enlaces **consumibles por clientes**; nunca expone información de
almacenamiento interno (hashes, rutas físicas, CDN, R2, IPFS...).

## Endpoints

| Método | Path | Descripción |
|--------|------|-------------|
| `GET` | `/api/search` | Busca y devuelve **Works completas**. |
| `GET` | `/api/lookup` | Autocompletado: solo índice (mínimo para localizar). |
| `GET` | `/api/resource/{id}` | Una Work completa (mismo DTO que `search`). |
| `GET` | `/api/download/{resource_id}` | Resuelve y descarga (stream o redirect) un recurso físico. |
| `GET` | `/api/version` | Versión del contrato. |

## LOOKUP — `GET /api/lookup?q=...`

Optimizado para **autocompletado**. **No** consulta metadata ni recursos. Devuelve únicamente la
información mínima para localizar una obra:

```json
{
  "works": [
    {
      "id": 264,
      "title": "Contredanse in F, K. 15h",
      "composer": "W.A. Mozart",
      "catalogue": "K. 15h",
      "confidence": 1.0
    }
  ]
}
```

Cada elemento contiene únicamente: `id`, `title`, `composer`, `catalogue`, `confidence`.
No devuelve `metadata`, `resources` ni `statistics`. Debe ser **extremadamente rápido**
(usa exclusivamente el índice).

## SEARCH — `GET /api/search?q=...`

Endpoints principal. Devuelve **siempre Works completas**; nunca requiere llamadas posteriores para
completar una Work. **No existe** "search ligero" ni `include`.

Cada `Work` contiene toda la información conocida por Storage:

- **Identidad**: `id`, `title`, `composer`, `composer_id`, `catalogue`, `aliases`
- **Metadata**: `subtitle`, `artist`, `song_name`, `opus`, `musical_key`, `duration`, `measures`,
  `pages`, `parts`, `complexity`, `license`, `public_domain`, `description`, `thumbnails`,
  `genres`, `tags`, `instruments`, `parts_names`
- **Statistics**: `favorites`, `downloads`, `views`, `rating`
- **Resources**: los ficheros descargables conocidos por Storage (no "Representations"; será
  OSAP-API quien los transforme). Cada recurso: `id`, `format`, `mime_type`, `available`,
  `license` y `links` (`download`, `view`, `thumbnail`).

```json
{
  "works": [
    {
      "id": 264,
      "title": "Contredanse in F, K. 15h",
      "composer": "Wolfgang Amadeus Mozart",
      "composer_id": "8f5b3a7e",
      "catalogue": "K. 15h",
      "aliases": [],
      "metadata": {
        "subtitle": null,
        "artist": null,
        "song_name": "The London Sketchbook 15a - 15ss",
        "opus": null,
        "musical_key": "F major",
        "duration": "00:53",
        "measures": 25,
        "pages": 2,
        "parts": 1,
        "complexity": null,
        "license": "cc-zero",
        "public_domain": true,
        "description": "Contredanse del London Sketchbook",
        "thumbnails": "{...}",
        "genres": ["classical"],
        "tags": ["contredanse", "chamber"],
        "instruments": ["piano"],
        "parts_names": ["Piano"]
      },
      "statistics": { "favorites": null, "downloads": null, "views": null, "rating": null },
      "resources": [
        {
          "id": "100654",
          "format": "PDF",
          "mime_type": "application/pdf",
          "available": true,
          "license": "cc-zero",
          "links": {
            "download": "/api/download/100654",
            "view": null,
            "thumbnail": null
          }
        }
      ]
    }
  ]
}
```

`links.download` es una ruta **resoluble por Storage** (`/api/download/{resource_id}`): oculta el
CDN, R2, disco, IPFS y los hashes. `view` y `thumbnail` quedan reservados para enlaces públicos.

## RESOURCE — `GET /api/resource/{id}`

Devuelve **exactamente el mismo DTO que `search`**, pero para un único `id`:

```json
{ "work": { "id": 264, "title": "...", "composer": "...", "composer_id": "...", "catalogue": "...", "aliases": [],
            "metadata": { ... }, "statistics": { ... }, "resources": [ ... ] } }
```

## IDENTIDAD CANÓNICA DE COMPOSITORES

`composer_id` es el **identificador canónico** de un compositor mantenido por Storage. El campo
`composer` contiene su **nombre canónico**. La resolución es responsabilidad exclusiva de Storage,
no de OSAP-API ni del `mapping.yaml` de cada proveedor.

```
PROVEEDOR  →  composer = "Mozart, W. A."
Storage    →  composer_aliases  →  composer_id  →  composers → Work.composer / Work.composer_id
```

- **`composer`**: nombre canónico del compositor (p. ej. `"Wolfgang Amadeus Mozart"`).
- **`composer_id`**: UUID estable y opaco de la identidad canónica (p. ej. `"8f5b3a7e"`).
- **`composer_aliases`**: tabla de nombres conocidos (`alias`) con su forma normalizada
  (`normalized_alias`). Un mismo `normalized_alias` no puede apuntar a dos compositores
  (`UNIQUE`); si se detecta ese conflicto, se trata como un **conflicto de datos** y no se
  resuelve arbitrariamente.

Distintos proveedores pueden usar nombres distintos para el mismo compositor (OMR
`"Wolfgang Amadeus Mozart"`, IMSLP `"Mozart, W. A."`, OpenScore `"W. A. Mozart"`) y todos
terminan resolviéndose al mismo `composer_id`.

Cuando un nombre **no puede resolverse**, Storage **no crea** un compositor nuevo: devuelve

```json
{ "composer": "Algún compositor desconocido", "composer_id": null }
```

La creación y asociación de nuevos compositores se controla posteriormente desde administración,
para no llenar la tabla con errores procedentes de proveedores. La administración de la identidad
canónica (listado, detalle, candidatos y fusión de compositores) vive en los endpoints
`/api/admin/composers*`; ver `docs/composer-administration-v1.md`.

### Población inicial

Las tablas `composers` / `composer_aliases` se crean **vacías** (sin datos inventados) en la
migración. Para poblarlas de forma segura se recomienda un proceso admin idempotente:

1. Añadir el compositor canónico a `composers` (con su UUID y nombre canónico).
2. Añadir a `composer_aliases` cada nombre conocido (incluido el canónico), siempre con su
   `normalized_alias`. Si un `normalized_alias` ya existe para otro compositor, `add_alias`
   lanza `DuplicateComposerAlias` (conflicto de datos) en lugar de resolver arbitrariamente.
3. Al añadir un alias nuevo, las futuras Works que contengan ese nombre se resuelven de inmediato
   al mismo `composer_id` (no hay proceso de re-importación).

Hay un comando CLI que automatiza la población desde un CSV de PDMX (p. ej. la copia del mirror
en `G:\osap-storage\PDMX.csv`):

```
osap-storage populate-composers G:\osap-storage\PDMX.csv
```

El proceso agrupa los nombres de compositor por su `normalized_alias`, elige un **nombre canónico
determinista** para cada grupo (el más frecuente, desempate al más largo) y crea el compositor con
un UUID + su alias canónico. Es **idempotente**: al repetirlo reutiliza los existentes. No aplica
ningún algoritmo de "mejor compositor": dos formas normalizadas distintas quedan como compositores
separados hasta que la administración los fusione. Para producción se recomienda generar antes un
CSV compacto de nombres (solo la columna de compositor) y copiarlo al servidor:

```
scripts\export_composer_names.ps1 -Source G:\osap-storage\PDMX.csv -Out G:\osap-storage\composer_names.csv
scp G:\osap-storage\composer_names.csv ocw@91.134.255.134:/tmp/composer_names.csv
osap-storage populate-composers /tmp/composer_names.csv   # en el servidor
```

## DOWNLOAD — `GET /api/download/{resource_id}`

Storage **resuelve internamente** el recurso físico y responde con un **stream** o un **redirect**
(302). El `resource_id` pertenece al **Resource**, no a la Work. OSAP-API **nunca** construye URLs:
solo consume el enlace generado por Storage.

## MODELO

Una `Work` debe ser **autocontenida**. No se obliga al consumidor a realizar llamadas adicionales.

## Validaciones del contrato

- `lookup` utiliza **exclusivamente el índice** (sin metadata ni recursos).
- `search` **no** realiza llamadas N+1 (usa consultas por lote).
- `resource` **reutiliza exactamente** el DTO de `search`.
- `download` **nunca** expone hashes ni rutas internas (solo un redirect/stream a un enlace consumible).
- **Ningún DTO** contiene conceptos de OSAP-API (Work Resolution, Matching Works, Relationships,
  RepresentationInfo).

## Códigos de Error (HTTP)

| Código | Descripción |
|--------|-------------|
| 400 | Parámetros incorrectos |
| 404 | Recurso/Work no encontrado |
| 500 | Error interno |

## Versionamiento

- `GET /api/version` → `{ "contract": "osap-provider-v1", "version": "1.0" }`

---
*Documento del contrato v1.3 (2026-08) — proveedor de información puro.*
