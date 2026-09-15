# Propuesta de diseño — `works` y apoyos (osap-storage_new) — V3 (acordada)
> Actualización V2 en `docsNew/diseño-works-propuesta.md`.
> **Personas y lo que no sea `works` queda para más adelante.** Cerramos primero `works`.

---

## Normativa (aplica a TODO)
Las columnas de cada tabla empiezan por el conjunto de letras del nombre de la tabla. **Excepción deliberada**: cuando una columna es FK a otra tabla, mantiene el prefijo de la tabla que referencia (no la propia). Ejemplo: en `works_voicings`, `works_id` referencia `works.id`.

---

## 1. `works` — representación concreta de una obra musical (un formato = un work)

```
works
────────────────────────────────
id
works_song_name
works_title
works_subtitle

works_attr_type                 ANONIMA, TRADICIONAL, POPULAR, ATRIBUIDA
works_attribution_note

works_opus
works_catalogue                 identificador de catálogo correctamente formateado

works_musical_key
works_year
works_epoch_id                  FK → epochs.id
works_duration
works_measures
works_pages
works_parts
works_complexity

works_description
works_license
works_public_domain

works_origin                    proveedor/fuente (proveedor o email de usuario, ver decisión abajo)
works_origin_id                 identificador del registro en ese origen

works_type_file                 id de tipo de fichero (FK a tabla futura de tipos)
works_obra_iden                 autoreferencia (gestión de grupos de works)

works_relative_path
works_music_digest
```

**Retirados de la V1/V2:**
- `works_n_edition` (eliminado).
- `works_language_id` → se sustituye por junction `works_languaje`.
- `works_voicing` → se sustituye por junction `works_voicings`.

**Observaciones:**
- `works_origin` / `works_origin_id`: ver decisión al final.
- `works.catalogue` almacena el **identificador de catálogo correctamente formateado** (p. ej. `BWV 846`, `K. 15h`), no el nombre del catálogo. Se reconoce mediante la tabla `catalogs` (ver más abajo).
- Se mantienen `works.genre` (TEXT) y `works.tags` (TEXT); normalización a `work_genres`/`tags_work`/`work_tags` vendrá después.

### Decisión sobre `works_origin` / `works_origin_id`
- `works_origin`: VARCHAR que contiene bien un **nombre de proveedor/fuente** (`PDMX`, `OMR`, `CPDL`, `MUSICBRAINZ`, …) o bien un **correo electrónico** cuando la canción la manda directamente un usuario.
- Reconocimiento de envío de usuario: si `works_origin` tiene formato de email (contiene `@`), se trata como envío de usuario; en ese caso `works_origin_id` será el **id del usuario en nuestra BD** (o el email como alternativa temporal).
- Sin FK obligatoria a `providers`.

---

## 2. `catalogs` — catálogos temáticos: patrones de reconocimiento
La misión de `catalogs` es **ayudar a reconocer si el título indica un catálogo** y extraer el identificador correctamente formateado. No es la misma tabla que `catalogues` (actual).

```
catalogs
────────────────────────────────
id
name                        Op, WoO, BWV, K, HWV, RV, Hob, ...
regex_pattern               para detectar el catálogo en el título
format_template             para normalizar el identificador (ej. BWV {1})
description
```

Ejemplos de catálogos: Op/Opus, WoO (Werke ohne Opuszahl), BWV (Bach-Werke-Verzeichnis), K (Köchel-Verzeichnis), HWV (Händel-Werke-Verzeichnis), RV (Ryom-Verzeichnis), Hob (Hoboken-Verzeichnis).

**Uso:** al analizar `works.title`/`works.catalogue`, se aplica el `regex_pattern` del catálogo correcto para extraer y formatear el identificador que se guarda en `works.works_catalogue`.

> ⚠️ Relación con la tabla `catalogues` actual de la BD: distintas. Definir si coexisten o se sustituyen.

---

## 3. `cpdl_works` (procesamiento de CPDL)
- Misma estructura/columnas que `works` (prefijo `cpdl_`).
- `cpdl_works.origin = 'CPDL'`; `cpdl_works.origin_id = 0`.
- **Cuidado con `payload_json`:** puede contener más de una obra teóricamente idéntica → puede obligar a crear **varios registros** de `cpdl_works`. En ese caso `works_obra_iden` indica cuál es el primero.
- Tras procesar, se integra en `works` (vía `works_obra_iden`).

---

## 4. `voicings` + `works_voicings` (sustituye `works_voicing`)
`works_voicing` se retira de `works` porque una partitura puede prepararse para **varios sistemas de voces**.

- **`voicings`** — se crea a partir de `cpdl_voicing`: columnas `id`, `term` (renombrado a `nombre`). **Un registro por término distinto**.
- **`works_voicings`** — junction N:N: `works_id`, `voicing_id`.

---

## 5. `languages` + `works_languaje` (sustituye `works_language_id` en works)
- **`languages`**: `id`, `lng_texto`.
- **`works_languaje`** (junction): `works_language_id` (→ `works.id`), `language_id` (→ `languages.id`).

---

## 6. `works_obra_iden` — autoreferencia
Relación N:N entre `works` (representaciones de la misma obra/versión/arreglo). Definir después (grupos >2 works, mapeo JSON CPDL).

---

## 7. `works_persona` — relación work ↔ persona
```
works_persona
────────────
work_id       FK → works.id
persona_id    FK → personas.id (personas se creará después)
role          FK → roles_person.id (ver más abajo)
```
- La atribución se representa a través de `role`.

---

## 8. Roles de persona (`roles_person`) — a diseñar
Lista de roles proporcionados (agrupados por ámbito). La tabla `roles_person` tendrá `id` y `role_name`; `works_persona.role` será FK a ella. **Pendiente cerrar la tabla y la lista.**

**1. Composición y autoria**
- COMPOSER — Creador/a original de la música (melodía, armonía, estructura).
- LYRICIST / LIBRETTIST — Autor/a del texto literario (óperas, oratorios, cantatas, Lieder, himnos).
- ARRANGER — Adapta la obra original para plantilla/formación distinta.
- ORCHESTRATOR — Escribe la particela y distribución tímbrica para orquesta a partir de un guion/boceto.
- TRANSCRIBER — Traslada notación antigua (tablatura, mensural) a moderna, o entre medios manteniendo fidelidad.
- EDITOR / REVISOR — Musicólogo/a que revisa manuscritos para edición crítica (Urtext), corrigiendo errores o añadiendo indicaciones.
- COMPLETER — Finaliza una obra inacabada tras la muerte del autor (Süssmayr/Mozart, Alfano/Puccini).

**2. Ejecución e interpretación**
- CONDUCTOR / CHORAL DIRECTOR — Lidera y coordina la ejecución del ensemble.
- PERFORMER / SOLOIST — Instrumentista o cantante que ejecuta la obra.
- KAPELLMEISTER — Responsable histórico de programar, ensayar y dirigir en institución eclesiástica/cortesana.
- VOCAL COACH / REPETITEUR — Pianista/asistente que ensaya con cantantes/coro antes del ensayo general.

**3. Vinculación social, histórica y económica**
- DEDICATEE — Persona a quien el compositor dedica oficialmente la obra (consta en portada).
- PATRON / COMMISSIONED BY — Persona/institución que financió la creación mediante encargo pagado.
- INSPIRED BY / MUSE — Persona en quien se basa la temática o carga emocional de la composición.

---

## 9. Atribución (se mantiene en `works`)
- `works_attr_type`: ANONIMA, TRADICIONAL, POPULAR, ATRIBUIDA.
- `works_attribution_note`.

---

## 10. Géneros — estructura intacta
```
works  →  work_genres  →  genre_mappings  →  genres
```
- `genres` y `genre_mappings`: **copiados tal cual**.
- `work_genres`: **se construirá después**, usando `works.genre`.

---

## 11. Instrumentos — estructura intacta
- `work_instruments` (`work_id`, `instrument_id`) — junction N:N.
- `instruments` (catálogo) y `instruments_categories` (jerarquía). `instruments.category_id` → `instruments_categories.id` (N:1).

---

## 12. Tags — pendiente
- `tag_work` (catálogo: `id`, `tag_text`): **se creará después**.
- `work_tags` (junction): **se construirá después**.
- `works.tags` (TEXT) se mantiene por ahora.

---

## 14. `work_statistics` — información derivada
Prefijo `wksta_`:
```
work_id
wksta_vote_count
wksta_work_count
wksta_confidence
wksta_rating
wksta_adjusted_rating
wksta_calculated_at
```

---

## Tablas no mencionadas (sin acción)
Subsistema de almacenamiento (`archives`, `archive_entries`, `files`, `storage_locations`, `storage_providers`, `download_jobs`, `import_sources`, `statistics`, `statistics_runs`), `votes`, `authority_identifiers`, `authority_sync_state`, `catalogues` (actual, ver ⚠️ en catalogs), `epochs`, `musicbrainz_cache`, `schema_migrations`, y derivados de `composers` (personas después).
