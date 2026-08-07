# OSAP Provider API Contract v1.3

## Introducción
Este documento define el contrato públicamente estable para integraciones entre OSAP y los proveedores de recursos musicales. Cualquier proveedor que implemente esta API es automáticamente compatible con OSAP sin requerir cambios internos en el sistema.

> **v1.3**: registra el **formato de Work enriquecida** (Metadata Enrichment) y la respuesta de **dos niveles**
> (búsqueda ligera vs. resolución enriquecida). Compatible hacia atrás con v1.2.

## Endpoints Base
| Método | Path | Descripción |
|--------|------|-------------|
| `POST` | `/api/license` | Establece términos de licencia |
| `GET`  | `/api/search` | Busca recursos (Works ligeras) |
| `GET`  | `/api/resource/{id}` | Obtiene una Work completa (según `include=`) |
| `GET`  | `/api/representations/{id}/download` | Descarga una representación (stream) |
| `GET`  | `/api/version` | Retorna versión del contracto |

## Parámetros Comunes

### Búsqueda (`GET /api/search`)
```json
{
  "schema": "object",
  "properties": {
    "q": {"type": "string", "description": "Texto de búsqueda libre"},
    "composer": {"type": "string"},
    "catalog": {"type": "string"},
    "type": {
      "type": "string", 
      "enum": ["score", "audio", "video", "lyric", "all"]
    },
    "page": {"type": "integer", "minimum": 1},
    "per_page": {"type": "integer", "maximum": 100}
  }
}
```

### Respuesta de Búsqueda
```json
{
  "query": { /* parámetros de búsqueda originales */ },
  "total": 42,
  "resources": [
    {
      "id": "res_abc123",
      "title": "Ave Verum Corpus",
      "provider_id": "omr-v3",
      "composer": "Wolfgang Amadeus Mozart",
      "catalog": "K. 618",
      "type": "score",
      "formats": ["xml", "pdf"],
      "access": {
        "mode": "direct",
        "license": "CC BY-SA",
        "url": "https://repository.org/scores/ave-verum.xml",
        "expires": "2025-01-01T00:00:00Z"
      }
    }
  ]
}
```

## Work enriquecida — Metadata Enrichment (v1.3)

**Filosofía:** el proveedor devuelve **entidades musicales enriquecidas** (`Work`). OSAP-API construye
la **Work Resolution** a partir de esas entidades.

> **Nota clave (arquitectónica):** El proveedor **nunca** devuelve una Work Resolution. Devuelve
> entidades `Work` enriquecidas. La construcción de Matching Works, Work Resolution, Relationships
> y Knowledge Hub corresponde **exclusivamente a OSAP-API**.
>
> Esta separación evita que, en el futuro, se intente mover lógica de resolución a Storage.

### Separación de responsabilidades

| Componente | Responsable de |
|---|---|
| osap-storage (proveedor) | Conocer dónde están físicamente los ficheros (R2, CDN, disco, IPFS...), **generar las URLs/tokens de descarga** y exponer las representaciones. |
| osap-api | Resolver obras, fusionar proveedores, construir la Work Resolution y exponer una API unificada. **No sabe dónde vive un fichero** ni cómo generar URLs. |
| Frontend | Nunca conocer hashes ni rutas físicas; solo consume `representation_id`. |

**Quién genera las URLs: osap-storage** (el propietario del repositorio). osap-api únicamente copia
esos campos en su `RepresentationInfo`; no construye URLs a partir de `relative_path` (no conoce el
CDN, la estructura de directorios, R2 ni los hashes).

### Niveles de información

**Nivel 1 — índice (lo mínimo para buscar):**
`id`, `composer`, `title`, `catalogue`, `aliases`.

**Nivel 2 — metadata musical (extraída del JSON de la fuente):**
`subtitle`, `artist`, `song_name`, `opus`, `musical_key` (tonalidad), `duration`, `measures`,
`pages`, `parts`, `complexity`, `license`, `public_domain`, `description`, `thumbnails`,
`genres` (lista), `tags` (lista), `instruments` (lista), `parts_names` (lista).

**Nivel 3 — representación (por recurso, no por obra):** `format`, `license`, `voices`,
`compressed`, `validated`, `mime_type`.

### Origen de la metadata
- El índice inicial procede del **CSV** de la fuente.
- La metadata musical se **enriquece** a partir del **JSON** (p. ej. el JSON de MuseScore por obra).
- El **JSON original se conserva** como documento fuente (no se guarda entero en la BD); en la base
  solo se extraen los campos necesarios.

### Flujo

```
GET /api/search                          → Works ligeras (solo para localizar)
GET /api/resource/{id}                   → Work + Metadata + Statistics + Representations (según include=)
GET /api/representations/{id}/download   → stream
```

### Búsqueda (siempre ligera)
`GET /api/search` devuelve **únicamente** lo mínimo para localizar (sin metadata, statistics ni
representations):
```json
{
  "works": [
    { "id": 264, "title": "Contredanse in F, K. 15h", "composer": "W.A. Mozart", "catalogue": "K. 15h", "confidence": 0.98 }
  ]
}
```

### Recurso (endpoint rico)
`GET /api/resource/{id}` devuelve **toda** la información enriquecida, según `include=`:
- `GET /api/resource/264`
- `GET /api/resource/264?include=metadata`
- `GET /api/resource/264?include=representations`
- `GET /api/resource/264?include=metadata,representations,statistics`

Formato de `include` (lista separada por comas):
```
include = metadata[,representations][,statistics]
```

**Comportamiento por defecto:** si no se especifica `include`, el proveedor devuelve **únicamente**
el objeto `work`.

Ejemplo (con `include=metadata,representations`): `work`, `metadata`, `statistics` y
`representations` son **objetos de nivel superior** (independientes; `work` no crece
indefinidamente):
```json
{
  "work": { "id": 264, "title": "Contredanse in F, K. 15h", "composer": "W.A. Mozart", "catalogue": "K. 15h" },
  "metadata": {
    "subtitle": null,
    "song_name": "The London Sketchbook 15a - 15ss",
    "opus": null,
    "musical_key": "F major",
    "duration": "00:53",
    "measures": 25,
    "pages": 2,
    "parts": 1,
    "license": "cc-zero",
    "public_domain": true,
    "description": "...",
    "thumbnails": "{...}",
    "genres": ["classical"],
    "tags": ["contredanse", "chamber"],
    "instruments": ["piano"],
    "parts_names": ["Piano"]
  },
  "statistics": { "favorites": 1, "downloads": 0, "views": 300, "rating": 0 },
  "representations": [
    {
      "id": "rep_100654_pdf",
      "format": "PDF",
      "available": true,
      "license": "cc-zero",
      "mime_type": "application/pdf",
      "links": { "download": "https://cdn.../pdf/....pdf", "view": "...", "thumbnail": "..." }
    }
  ]
}
```

Nota: `confidence` pertenece a **Search** (evaluación de candidatos); en `resource/{id}` no tiene
sentido (ya no se evalúan candidatos), por lo que no aparece en este endpoint.

### Representaciones
El DTO de representación **no expone rutas físicas** (`relative_path`, `source_url`, `hash`), sino
**únicamente enlaces públicos** (`links`) generados por el proveedor. El cliente no necesita conocer
rutas ni hashes. Estilo HAL / JSON:API:
```json
{
  "id": "rep_100654_pdf",
  "format": "PDF",
  "available": true,
  "license": "cc-zero",
  "mime_type": "application/pdf",
  "links": { "download": "...", "view": "...", "thumbnail": "..." }
}
```
La URL la genera **osap-storage**. Si se quiere ocultar por completo el CDN, `links.download` puede
ser una ruta relativa (`/api/representations/{id}/download`) que resuelve el propio proveedor.

### Estadísticas
`favorites`, `downloads`, `views`, `rating` son **opcionales** (cada proveedor tiene métricas
distintas; un proveedor puede no tener ninguna).

### Por qué `include=` en `/resource/{id}`
Evita el patrón N+1 al obtener una ficha completa en una única llamada, sin que el buscador
transportee información pesada:
```
Antes:  resource → metadata → representations → statistics (4 llamadas)
Ahora:  resource/{id}?include=metadata,representations,statistics → 1 llamada
```

**OSAP-API**, a partir de los datos de este contrato:
```
Search → Matching Works → Work Resolution → Relationships → Knowledge Hub
```



## Códigos de Error (HTTP)
| Código | Error        | Descripción                              |
|--------|--------------|------------------------------------------|
| 400    | InvalidRequest | Parámetros incorrectos                 |
| 401    | AuthRequired | Requiere autenticación                 |
| 403    | Forbidden    | Credenciales inválidas/quota agotado    |
| 404    | NotFound     | Recurso no encontrado                 |
| 429    | RateLimited  | Demasiadas solicitudes                 |
| 500    | ServerError  | Error interno del proveedor            |

## Autenticación
Usar Basic Auth en encabezado `Authorization`:
```
Authorization: Basic Om15cGFzc3dvcmQ=
```

Claves API para alta demanda:
```
X-API-Key: my_provider_api_key
```

## Paginación
Siempre usar paginación estilo cursor:
```json
{
  "pagination": {
    "next_cursor": "dXNlcjpVMEc5V",
    "prev_cursor": "dXNlcjpXQklK",
    "total_pages": 5,
    "current_page": 2
  }
}
```

## Versionamiento
El modelo sigue SemVer estricto (MAJOR.MINOR.PATCH). Cambios en:
- MAJOR: Cambios incompatibles
- MINOR: Nuevos features compatibles
- PATCH: Correcciones compatibles

## Compatibilidad hacia atrás
Todos los endpoints requieren:
```http
Accept: application/vnd.osap-api.v1.3+json
```

## Garantías
1. Las URLs de acceso serán válidas por mínimo 60 días
2. Los metadatos conservarán formato estable
3. El ID de recurso persistirá permanentemente

---
*Documento congelado para uso público - v1.3 (2026-08)*