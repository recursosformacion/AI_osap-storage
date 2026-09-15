# Revisión del diseño `works` (osap-storage_new) — V3
> Actualización V2 en `docsNew/diseño-works-revision.md`.
> **Personas y lo no-`works` queda para después.** Cerramos `works`.

---

## ✅ Resuelto en esta sesión

| Punto | Decisión |
|---|---|
| Normativa de prefijos | Aplica a todo; FK mantienen prefijo de tabla referenciada (`work_id`, `works_id`…). |
| `works_epoch` | → `works_epoch_id` (FK → `epochs.id`). |
| `works_language_id` | Eliminada de `works`. Nuevas tablas: `languages(id, lng_texto)` + junction `works_languaje(works_language_id, language_id)`. |
| `works_voicing` | **Retirada** de `works` (una partitura puede tener varias voces). Nuevas tablas: `voicings(id, nombre)` — derivada de `cpdl_voicing` (un registro por término) + junction `works_voicings(works_id, voicing_id)`. |
| `works_n_edition` | **Retirada**. |
| `catalogs` | Tabla de reconocimiento de catálogos: `id, name, regex_pattern, format_template, description`. Usa regex para extraer el identificador correctamente formateado que va en `works.works_catalogue`. Distinta de `catalogues` (actual). |
| `works_origin` / `works_origin_id` | **Decisión:** VARCHAR con proveedor (`PDMX`,`OMR`,`CPDL`…) o email (reconocible por `@`) para envíos de usuario; `origin_id` = id del registro en ese origen (string). Sin FK a `providers`. |
| `works_type_file` | Por ahora id; tabla de tipos de fichero después. |
| `works_obra_iden` | Autoreferencia (detallar después). |
| `works_persona` | 3 columnas: `work_id`, `persona_id`, `role` (FK a `roles_person`). |
| `roles_person` | Tabla a diseñar con la lista de roles proporcionada (3 ámbitos: composición, ejecución, vinculación social). **No cerrada** (sin id/structura final). |
| `cpdl_works` | Misma estructura que `works`; `origin='CPDL'`, `origin_id=0`. Cuidado con `payload_json` (puede forzar varios registros, enlazados por `works_obra_iden`). |
| `work_genres` | Se construye después, usando `works.genre`. |
| `work_statistics` | Prefijo `wksta_`. |
| `tag_work` | Se creará después. |
| `genres`, `genre_mappings` | Copiados tal cual. |
| `work_instruments`, `work_tags` | Mantenidos como junctions N:N. |

---

## ⚠️ Puntos que necesitan cierre antes de crear `works`

1. **`works_languaje` junction** — definir PK y FKs exactas: `(works_language_id, language_id)` o `(work_id, language_id)`? El nombre `works_language_id` dentro de `works_languaje` es ambiguo. Confirmar.
2. **`catalogs` vs `catalogues`** — la BD actual tiene `catalogues(id, prefix, composer, catalogue_name, creator, ordering_criterion)`. La nueva `catalogs(id, name, regex_pattern, format_template, description)` es distinta (patrones de reconocimiento). ¿Coexisten? ¿`catalogues` se sustituye o se complementa? Definir antes de crear `catalogs`.
3. **`voicings` tabla** — derivada de `cpdl_voicing` (id, nombre). ¿`cpdl_voicing` se elimina o se mantiene como origen? Definir si es migración o tabla paralela.
4. **`works_voicings` junction** — columnas: `works_id`, `voicing_id` o `work_id`? Alinear con normativa.
5. **`works_obra_iden`** (autoreferencia) + flujo `cpdl_works`/`payload_json` — sin columnas ni reglas definidas. Punto más frágil.
6. **`roles_person`** — tabla pendiente; la lista de roles ya está (3 ámbitos, 18 roles) pero falta `id`/estructura y si hay categorías.
7. **`work_genres` mapping** — ¿cómo se mapea `works.genre` (TEXT) → `genre_mappings`? ¿Tabla intermedia o match directo?
8. **`tag_work`** / `work_tags` — al crearse, definir columnas y FK.
9. **`work_statistics`** — `work_id` sin prefijo `wksta_` (¿OK o `wksta_work_id`?). Confirmar.

---

## 🧭 Despistes que vigilaré

- **`catalogs` puede romper el flujo actual** que usa `catalogues` (BD actual). Ver si `works.catalogue` se nutre de `catalogs` (regex) o de `catalogues`.
- **`voicings`/`works_voicings`** — el código actual lee `cpdl_pages.voicing` y `cpdl_voicings`; asegurar la transición al nuevo modelo.
- **`works_origin` como email** — buscar emails en texto libre tiene coste; considerar prefijo `USER:` + email si crece el volumen.
- **`works_voicings` vs normativa** — asegurar que las FK en junctions sigan la regla de prefijo acordada.

---

## 📋 Próximos pasos (sin decidir)
1. Cerrar `works_languaje` (Punto 1).
2. Cerrar `catalogs` vs `catalogues` (Punto 2).
3. Cerrar `voicings`/`works_voicings` (Puntos 3-4).
4. Cerrar `works_obra_iden` + flujo `cpdl_works` (Punto 5).
5. Cerrar `roles_person` (Punto 6) y `work_genres` mapping (Punto 7).

Cuando quieras, dame decisiones de 1-5 y actúo. No he creado nada ni en BD ni en código.
