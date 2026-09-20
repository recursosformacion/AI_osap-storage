# Fase 7 — CRUD `representations` (2026-09-19)

Primer CRUD completo de la Fase 7 (metodología: diagnóstico → implementación → verificación → cierre).

## Backend (implementado)
`api/routes/admin_representations.py` + `SqlRepresentationAdminRepository` +
`RepresentationAdminCrud` + schemas:

| Endpoint | Descripción |
|---|---|
| `GET /api/admin/representations` | listado con filtros `origin`, `license`, `works_id`, `q`; paginación; cuenta recursos y editores |
| `GET /api/admin/representations/{id}` | ficha: representación + **recursos** + **editores** + **obra** |
| `POST /api/admin/representations` | alta (valida `works_id` + `origin`); UNIQUE `(origin, origin_id)` |
| `PUT /api/admin/representations/{id}` | edición |
| `DELETE /api/admin/representations/{id}` | borrado (cascada a recursos/editores) |

## Verificación
- **En vivo**: `GET ?origin=cpdl&limit=3` → `total=81983`; detalle `4560:3763` → `type=edition`,
  **2 recursos**, **1 editor**, obra `254036`, `url` derivada CPDL presente.
- **Tests**: `tests/integration/test_api_contracts.py` +2 (listado/ficha y **round-trip**
  create→update→delete→404). **15 pasan** en el fichero · **296** en la suite completa · `ruff` limpio.

## Prueba funcional de la cadena desde `osap-api`
- **PDMX**: `OmrStorageFetcher` → `/api/search` → 50 works; `resources[0]` MusicXML `available=true`
  con `download` interno (`/api/download/{id}`).
- **CPDL**: `/api/search?corpus=cpdl&q=dido` → 20 works, **20 con representación** (`edition`,
  licencia CC-BY-NC-SA); recurso `available=true` y `download=/api/download/293739` →
  **302 a `https://www.cpdl.org/wiki/index.php/Special:FilePath/dido_and_aeneas_-_full_score.mxl`**.

**Cadena `work → representation → resource` operativa end-to-end** (interna para PDMX, externa para
CPDL).

## Pendiente (siguiente dentro de Fase 7)
- **UI dedicada** de `representations` (hoy cubierta por el CRUD genérico `TableList`/`RowForm`):
  listado con filtros, ficha con recursos/editores y alta/edición.
- Siguientes CRUD: `works_resources`, `persons`, `works`, uniones N:N.

## UI dedicada (2026-09-19)
- `frontend/src/pages/Representations.tsx`: listado con filtros (`origin`, `license`, `works_id`,
  `q`) + paginación; **ficha** con obra, **recursos leídos de `works_resources`** y **editores
  leídos de `representation_persons`**; alta/edición/borrado.
- Funciones de API en `frontend/src/api.ts` (`listRepresentations`, `getRepresentation`,
  `create/update/deleteRepresentation`).
- Ruta `/representations` en `App.tsx` + enlace en el menú.
- **Fallback SPA** en `api/main.py`: `/admin/{path:path}` devuelve `index.html` si no hay fichero
  (arregla enlaces profundos, que antes daban 404, también en rutas existentes), preservando los
  SSR (`/admin/obras`, `/admin/maestros`) y `/admin/assets`.

**Verificación UI**: `tsc --noEmit` limpio · `vite build` OK · `/admin/representations`,
`/admin/t/works` → 200 (HTML) · `/admin/assets/*` → 200 · SSR intactos · API `total=81983`.

**Módulo `representations` cerrado** (backend + UI), con la cadena probada end-to-end desde
`osap-api` y `ruff`+`pytest` (296) en verde.
