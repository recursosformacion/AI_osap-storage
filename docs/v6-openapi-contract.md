# OSAP Storage V6 — contrato OpenAPI con OSAP-API

> Propuesta contractual para implementar V6. Revisión: 2026-11-01. No es una implementación ni una prueba contra producción.

## 1. Reglas del contrato

- Único modelo: Work → Resource → File. Representation desaparece de rutas, DTO y dominio.
- Resource pertenece directamente a Work; File pertenece a un Resource.
- Work publicada debe tener al menos un Resource. Crear Work + primer Resource + publicar es una operación atómica.
- Resource admite cero Files; también puede tener varios Files (formatos del mismo material).
- IDs públicos opacos, estables y tipados. Work ID, Resource ID y File ID nunca se convierten ni interpretan como otro tipo.
- No exponer SHA-256, object_key, bucket, provider_id, StorageLocation ni StorageProvider.
- El adaptador R2 resuelve internamente el puntero físico directo guardado en File.
- Storage solo gestiona catálogo/material OMR incorporado. La federación IMSLP, CPDL, RISM y otras fuentes corresponde a OSAP-API.
- Autoría/compositoría pertenece a Work. Créditos de arreglo, edición, adaptación, interpretación y traducción pertenecen a Resource. Composer no es un rol válido en Resource.
- Procedencia, derechos y licencia pertenecen a Resource; no inferir titular desde compositor o uploader.
- Los contratos V5 basados en Representation, archive_entries o IDs numéricos ambiguos no forman parte de V6.

## 2. Convenciones

Base path propuesto: `/api/v6`. JSON UTF-8; fechas ISO-8601 UTC. Paginación con `limit` (1–100, default 50) y `cursor` opaco. Colecciones: `items`, `next_cursor`, `total` opcional.

Error común:
```json
{ "error": { "code": "resource_not_found", "message": "Resource not found", "details": {} } }
```

El API entre servicios requiere credencial de servicio. La autorización del usuario final se aplica en OSAP-API; Storage no confía en un user_id arbitrario recibido en el JSON. Las mutaciones usan ETag/If-Match o versión equivalente para evitar sobrescrituras.

## 3. DTO canónicos

### Work

```json
{
  "id": "wrk_opaque",
  "title": "Ave verum corpus",
  "subtitle": null,
  "catalogue": null,
  "year": null,
  "description": null,
  "language": null,
  "genres": [],
  "tags": [],
  "instruments": [],
  "voices": [],
  "ensembles": [],
  "parts": [],
  "composer_credits": [
    { "person_id": "per_opaque", "display_name": "Compositor", "role": "composer", "position": 1 }
  ],
  "reference_resource_id": null,
  "created_at": "2026-11-01T10:00:00Z",
  "updated_at": "2026-11-01T10:00:00Z"
}
```

Work contiene identidad, metadatos de catálogo, clasificaciones y autoría. No contiene licencia/derechos del material, uploader, URL ni File. reference_resource_id es opcional y solo puede apuntar a un Resource hijo; no implica original histórico.

### Resource

```json
{
  "id": "res_opaque",
  "work_id": "wrk_opaque",
  "title": null,
  "kind": "score",
  "description": null,
  "provenance": {
    "source_type": "omr",
    "source_name": "OMR",
    "source_record_id": null,
    "created_by": { "actor_type": "system", "actor_id": "importer" }
  },
  "rights": {
    "license": null,
    "rights_holder": null,
    "public_domain": null,
    "evidence_url": null
  },
  "credits": [
    { "person_id": "per_opaque", "display_name": "Editor", "role": "editor", "position": 1 }
  ],
  "attributes": {
    "format_family": "notation",
    "instrumentation": [],
    "voices": [],
    "ensemble_id": null,
    "language": null,
    "musical_key": null,
    "edition": null,
    "arrangement": null
  },
  "external_access": [],
  "files": [],
  "created_at": "2026-11-01T10:00:00Z",
  "updated_at": "2026-11-01T10:00:00Z"
}
```

kind propuesto: score, recording, edition, arrangement, transcription, performance, other. Los vocabularios definitivos se cierran antes del OpenAPI congelado. provenance describe origen/actor, no ubicación física. El actor usuario se obtiene del contexto autenticado. rights permanece null si se desconoce. credits no admite composer. attributes solo describe el Resource. Un Resource sin File sigue siendo válido. external_access no convierte un resultado federado en Resource OMR: solo describe acceso de un Resource ya incorporado.

### File

```json
{
  "id": "fil_opaque",
  "resource_id": "res_opaque",
  "name": "ave-verum.mxl",
  "format": "MusicXML",
  "mime_type": "application/vnd.recordare.musicxml+xml",
  "size_bytes": 123456,
  "status": "available",
  "created_at": "2026-11-01T10:00:00Z",
  "updated_at": "2026-11-01T10:00:00Z"
}
```

No incluye sha256, object_key, bucket, provider_id, locations ni URL física. Estados propuestos: registered, processing, available, failed. Dos Files con igual SHA siguen siendo registros independientes.

### Access

```json
{
  "file_id": "fil_opaque",
  "action": "download",
  "url": "https://storage.example/opaque-access-token",
  "expires_at": "2026-11-01T10:15:00Z",
  "content_disposition": "attachment"
}
```

El acceso se resuelve por separado del catálogo. No asumir que existencia de Resource implica descarga o que un File disponible admite view.

## 4. Lecturas

| Método y ruta | Contrato |
|---|---|
| GET /api/v6/works?q=&composer_id=&catalogue=&limit=&cursor= | Busca solo Works OMR |
| GET /api/v6/works/{work_id} | Work y todos sus Resources, sin filtrar por disponibilidad |
| GET /api/v6/resources/{resource_id} | Resource y todos sus Files; válido con cero Files |
| GET /api/v6/files/{file_id} | Metadatos públicos del File, sin datos físicos |
| POST /api/v6/files/{file_id}/access | Resuelve acceso download/view y devuelve Access |

Respuesta de listado: `{ "items": [], "next_cursor": null, "total": 0 }`. Detalle Work: `{ "work": {...}, "resources": [...] }`. La colección resources incluye todos los Resources, incluso URL-only o sin Files.

POST access acepta action (download/view) y, opcionalmente, TTL solicitado sujeto a política. No acepta provider_id ni object_key. El servidor elige backend y modo de acceso. Puede responder 404 si no existe o 409/422 si la acción no está permitida.

## 5. Escrituras

| Método y ruta | Operación y regla |
|---|---|
| POST /api/v6/works | Crear Work + primer Resource y publicar atómicamente; respuesta 201 WorkDetail |
| PATCH /api/v6/works/{work_id} | Modificar metadatos/autoría de Work; autorización de compositor aplicada por OSAP-API |
| POST /api/v6/works/{work_id}/resources | Añadir Resource a Work existente; no crear Work duplicada |
| PATCH /api/v6/resources/{resource_id} | Modificar solo ese Resource según permisos; no cambiar Work padre |
| PUT /api/v6/works/{work_id}/reference-resource | Asignar o retirar Resource de referencia; validar pertenencia |
| POST /api/v6/resources/{resource_id}/files | Registrar File o iniciar carga; puntero físico nunca procede de cliente público |
| DELETE /api/v6/files/{file_id} | Retirada lógica auditada; no borrar R2 como efecto implícito |

El creador de Resource se toma del actor autenticado, no de un campo user_id libre. Composer no obtiene permiso para modificar Resources creados por otros. La eliminación física R2 requiere una política y operación explícitas separadas.

## 6. Federación: responsabilidad de OSAP-API

Storage no acepta corpus all ni devuelve candidatos externos. OSAP-API combina:
- omr_work: Work canónica de Storage y sus Resources/Files;
- external_material: registro tipado por proveedor, conservando provider_id, source_id y discriminantes;
- provisional_group: agrupación efímera sin identidad canónica ni asociación persistente.

La reconciliación de fuente externa con Work OMR requiere revisión cuando exista incertidumbre. Solo la incorporación expresa del material crea Resource en Storage.

## 7. Errores y aceptación

HTTP: 200 lectura/actualización; 201 creación; 202 proceso asíncrono; 400 formato inválido; 401/403 autenticación/autorización; 404 entidad inexistente; 409 conflicto; 422 regla de dominio; 429 límite; 500/503 fallo de servicio.

Códigos de dominio: work_not_found, resource_not_found, file_not_found, resource_not_in_work, work_requires_resource, composer_role_not_allowed_on_resource, reference_resource_must_belong_to_work, file_access_unavailable, concurrent_update.

Pruebas obligatorias:
1. Work publicada siempre tiene Resource y alta inicial es atómica.
2. Resource sin File se devuelve sin inventar descarga.
3. Resource con múltiples Files devuelve todos.
4. IDs de Work/Resource/File no se resuelven cruzados ni colisionan semánticamente.
5. Dos Files con mismo SHA permanecen independientes.
6. Resource de referencia pertenece a su Work.
7. Composer en credits de Resource se rechaza.
8. Material externo de búsqueda no se crea automáticamente como Resource OMR.
9. DTO público no contiene SHA, object_key, bucket ni provider.
10. Reiniciar Storage conserva la resolución de IDs.
11. Migración no escribe, copia, borra ni renombra objetos R2.

## 8. Pendiente antes de congelar OpenAPI

1. Cerrar campos Work contrastando tabla completa y consumidores.
2. Cerrar vocabularios kind, roles de Resource y estados File.
3. Definir contexto autenticado OSAP-API→Storage y auditoría.
4. Definir carga directa/delegada, límites, formatos y jobs.
5. Elegir redirect, URL firmada o streaming como implementación de Access.
6. Definir política de retirada lógica y retención física.
7. Definir cursor/filtros e índices.
8. Alinear IDs opacos públicos con claves internas sin asumir ID numérico.
9. Generar OpenAPI 3.1 desde esquemas y validar con pruebas de contrato en entorno de desarrollo.

Los endpoints y DTO V5 (osap-provider-v1, /api/search, /api/resource, /api/download/{id}, representations y archive_entries) son legado pre-corte; no forman parte de V6 ni se mantienen como compatibilidad permanente.
