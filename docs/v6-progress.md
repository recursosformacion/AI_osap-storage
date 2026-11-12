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
