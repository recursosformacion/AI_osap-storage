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
