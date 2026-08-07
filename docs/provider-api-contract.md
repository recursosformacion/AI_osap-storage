# OSAP Provider API Contract v1.3

## Introducción
Este documento define el contrato públicamente estable para integraciones entre OSAP y los proveedores de recursos musicales. Cualquier proveedor que implemente esta API es automáticamente compatible con OSAP sin requerir cambios internos en el sistema.

> **v1.3**: registra el **formato de Work enriquecida** (Metadata Enrichment) y la respuesta de **dos niveles**
> (búsqueda ligera vs. resolución enriquecida). Compatible hacia atrás con v1.2.

## Endpoints Base
| Método | Path | Descripción |
|--------|------|-------------|
| `POST` | `/api/license` | Establece términos de licencia |
| `GET`  | `/api/search` | Busca recursos disponibles |
| `GET`  | `/api/resource/{id}` | Obtiene detalles específicos |
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

El proveedor (p. ej. OMR / osap-storage) puede devolver obras enriquecidas con metadata musical.
La entidad `Work` deja de ser un mero `{id, title, composer, catalogue}` y pasa a ser una **ficha de
conocimiento**.

### Campos de `Work` (nivel 1 y 2)

**Nivel 1 — índice (lo mínimo para buscar):**
`id`, `composer`, `title`, `catalogue`, `aliases`.

**Nivel 2 — metadata musical (extraída del JSON de la fuente):**
`subtitle`, `artist`, `song_name`, `opus`, `musical_key` (tonalidad), `duration`, `measures`,
`pages`, `parts`, `complexity`, `license`, `public_domain`, `description`, `thumbnails`,
`genres` (lista), `tags` (lista), `instruments` (lista), `parts_names` (lista).

**Nivel 3 — representación (por recurso, no por obra):** `format`, `license`, `voices`,
`compressed`, `validated`, `mime_type`, `relative_path`, `source_url`, `hash`.

### Origen de la metadata
- El índice inicial procede del **CSV** de la fuente.
- La metadata musical se **enriquece** a partir del **JSON** (p. ej. el JSON de MuseScore por obra).
- El **JSON original se conserva** como documento fuente (no se guarda entero en la BD); en la base
  solo se extraen los campos necesarios.

### Dos niveles de respuesta

**1) Búsqueda ligera** (`GET /api/search`) — para búsquedas rápidas:
```json
{
  "id": 264,
  "title": "Contredanse in F, K. 15h",
  "composer": "W.A. Mozart",
  "catalogue": "K. 15h",
  "confidence": 0.98
}
```

**2) Resolución enriquecida** (`GET /api/search?view=resolution` o `?include=metadata`) — construye
directamente la Work Resolution (Knowledge Hub), sin llamadas posteriores (evita el patrón N+1):
```json
{
  "id": 264,
  "work": {
    "title": "Contredanse in F, K. 15h",
    "composer": "W.A. Mozart",
    "subtitle": null,
    "song_name": "The London Sketchbook 15a - 15ss",
    "opus": null,
    "catalogue": "K. 15h",
    "musical_key": "F major",
    "duration": "00:53",
    "measures": 25,
    "pages": 2,
    "parts": 1,
    "complexity": 0,
    "license": "cc-zero",
    "public_domain": true,
    "description": "...",
    "thumbnails": "{...}"
  },
  "metadata": {
    "genres": ["classical"],
    "tags": ["contredanse", "chamber"],
    "instruments": ["piano"],
    "parts_names": ["Piano"]
  },
  "representations": [
    {
      "format": "MusicXML",
      "relative_path": "./mxl/1/30/QmbL2...mxl",
      "available": true,
      "url": "https://cdn.openmusicrepository.com/storage2017/mxl/1/30/QmbL2...mxl"
    },
    { "format": "PDF", "available": true, "url": "https://..." },
    { "format": "MIDI", "available": true, "url": "https://..." }
  ],
  "statistics": {
    "favorites": 1,
    "views": 300
  },
  "provider": "omr-v3"
}
```

La API devuelve el **WorkResolutionDTO** completo en una única llamada; el cliente (OSAP) no debe
reconstruirlo ni hacer decenas de peticiones adicionales.

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