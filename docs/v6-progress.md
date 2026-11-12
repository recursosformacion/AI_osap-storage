# V6 — estado de la rama `v6`

Rama de desarrollo de `osap-storage`; no se despliega a producción.

## Hecho (2026-11-12)

- `domain/entities/resource.py`: Resource V6 (Work, procedencia, licencia, URL externa,
  visibilidad, referencia, metadata).
- `domain/ports/resource_repository.py`: puerto de persistencia.
- `infrastructure/repositories/sql_resource_repository.py`: repositorio SQL de Resource.
- `infrastructure/db/migrations/026_v6_resources.sql`: crea `resources` y añade
  `files.resource_id`/`files.storage_key`. Es **aditiva**: no retira Representation ni
  `works_resources`.
- Migración aplicada solo en la base de desarrollo `osap_storage`; CRUD verificado.
- Pruebas: modelo + mapeo de filas (8).

## Siguiente

1. File V6: clave física opaca (`storage_key`) y fin de la derivación desde SHA-256.
2. Mapeo seco `representations` + `works_resources` → `Resource/File`, con informe de
   conflictos (sin escribir).
3. Corte V6, API `/api/v6`, índice y validación.
## Hecho (2026-11-12, continuación)

- File V6: `storage_key` opaco y `resource_id`; `object_key()` deja de derivar la clave
  cuando existe la copia literal (fallback SHA solo para ficheros legados hasta el corte).
- Repositorio SQL de File actualizado; pruebas de modelo y flujos de descarga/publicación.
- Simulación V6 (`scripts/v6_map_dry_run.py`) sobre el snapshot de desarrollo:

| Concepto | Valor |
| --- | ---: |
| Resources previstos | 601.627 |
| desde Representations | 336.018 |
| de referencia (Works sin material) | 265.609 |
| Files previstos | 254.035 |
| Filas sin Representation existente | 0 |
| Filas sin fichero ni URL | 0 |
| Ficheros compartidos | 0 |
| Ficheros sin clave física | 0 |

Los 265.609 Works sin material no son un error: V6 exige al menos un Resource y se propone
un **Resource de referencia sin File** por cada uno. Es determinista, sin IA. Los recuentos
son del snapshot de desarrollo; hay que repetir el informe sobre la copia de producción.
## Corte V6 sobre datos reales (2026-11-12)

- Tablas de producción cargadas en la copia de desarrollo (solo lectura en prod):
  576.479 Works, 81.983 Representations, 471.378 works_resources, 254.049 Files.
- Simulación: **602.283 Resources** (81.983 desde Representations, 254.035 standalone,
  266.265 de referencia) y **254.035 Files**; 0 conflictos de representación, fichero
  compartido o clave física.
- Mapeo aplicado en dev con `scripts/v6_apply_mapping.py --apply`:
  - 602.283 Resources creados y marcados con `legacy_kind`/`legacy_id`.
  - 254.035 Files enlazados a su Resource; 254.049 con `storage_key` copiada de
    `storage_locations`.
  - 81.983 Resources de Representation no tienen File (válido).
  - **14 Files sin Resource**: capturas PNG de administración (`2026-10-*.png`,
    `maspeqie.png`) sin `works_resources`; no son material de catálogo. Decidir archivar
    o borrar antes del corte.
- La tabla `resources` y las columnas V6 de `files` viven solo en dev.

## Siguiente

1. Resolver los 14 PNG huérfanos.
2. API `/api/v6` y reconstrucción del índice sobre Resources.
3. Corte y validación final (R2 intacto; sin borrar Representation hasta verificar).
## API V6 de lectura (2026-11-12)

- `/api/v6/works`: búsqueda de Works con Resources (`q`, `composer`, `catalogue`, `cursor`, `limit`).
- `/api/v6/works/{id}`: Work + Resources.
- `/api/v6/resources/{id}`: Resource + Files.
- `/api/v6/files/{id}`: metadatos públicos (sin `storage_key`).
- Aditiva sobre `/api/v1`; no expone claves físicas.
- Verificado contra la copia de producción en dev: Work 287062 con 22 Resources; búsqueda
  “Ave verum” con `resource_count`; Resource con File; File sin `storage_key`.
- 4 pruebas de mapeo de DTO.

## Pendiente

- Endpoints de escritura/acceso (`POST/PATCH`, `access`), autenticación de servicio.
- Reconstrucción del índice sobre Resources y corte final.
- Los 14 PNG huérfanos quedan fuera del catálogo V6 (sin Resource); archivar/borrar más adelante.
## Invariante Google (2026-11-12)

- Los IDs públicos de obra (`index-<works.id>`) y los títulos (`works_title`) **no se
  modifican** con el mapeo V6. El slug canónico sigue siendo `slugify(works_title)`.
- Comprobado con el sitemap real de producción (`/sitemaps/works-1.xml`, 500 URLs):
  - 0 Works ausentes en Storage.
  - 0 Works sin Resource V6.
  - 0 fallos HTTP en la muestra (URLs 200).
  - 334 slugs históricos (con compositor) difieren del canónico actual (solo título),
    pero siguen devolviendo 200. Es una discrepancia previa al corte, no de V6.
- Recomendación antes del corte: regenerar/limpiar la caché del sitemap y alinear
  sitemap y canónico; después ejecutar `v6_url_stability.py --strict`.
- El futuro índice V6 debe construir `index-<works.id>` y el slug desde `works_title`;
  cualquier limpieza de títulos exige tabla de correspondencia y 301.
## Acceso V6 (2026-11-12)

- `POST /api/v6/files/{file_id}/access` con `action` (`download`/`view`) y `ttl_seconds`.
  No acepta `provider_id` ni `object_key`; el servidor elige proveedor.
- Respuesta `{url, action, expires_at}`; la URL no contiene claves físicas (usa la URL
  nativa del proveedor o el endpoint interno de contenido).
- Verificado en dev: file 624 → 200 con URL de descarga.

## Siguiente

- Endpoints de escritura (`POST/PATCH` Work/Resource/File) con permisos.
- Reconstrucción del índice sobre Resources con `index-<works.id>` y slug desde
  `works_title` (invariante Google).
