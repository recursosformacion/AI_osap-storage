# Cierre — Módulo representaciones/recursos (2026-09-19)

Bloque **diagnosticado y cerrado sin transformación**. Base del diagnóstico:
`docsNew/diagnostico-representaciones-recursos.md`.

## Modelo canónico (fijado)
```
works ── representations ── representation_persons
                     └───── works_resources
works ── works_resources (work_id)
```
- **PDMX**: `work → resource` directo (1:1 con `files`; sin nivel de representación — op2).
- **CPDL**: `work → representation (edition) → resources` (varias ediciones por obra).

## Hechos aceptados (no son inconsistencias)
- **217.343 recursos CPDL sin `file_id` ni `url`** = **inventario pendiente de materialización**
  (decisión de producto/licencia posterior). No se transforman ahora.
- **11.242 representaciones sin recurso** = válidas como **inventario** (decisión §11).
- **0 duplicados** (`file_id`, `(representación,nombre,tipo)`).

## Legado/staging conservado
`archive_entries`, `cpdl_editions`, `cpdl_edition_files`, `cpdl_edition_persons` siguen presentes y
con **consumidores** (`SqlArchiveEntryRepository`, `import_pdmx`, fallback de `GetWork`/descarga).
**No se eliminan ahora.**

## Alcance
- **Sin transformación estructural ni escritura pendiente** en este módulo.
- **Materialización CPDL** = decisión independiente posterior (ver §"Corrección" abajo).

## Comprobación del origen CPDL (2026-09-19) — corrige el encuadre

Pregunta: ¿el origen contiene suficiente para **derivar la URL** de cada recurso, aunque no sea PDF?

- `cpdl_edition_files` guarda **solo `name` + `type`** (sin URL/path); 0 nombres con `/`, 1 con `http`.
- El **origen XML** (`G:\cpdl_chunks\cpdl-0.xml`) referencia los ficheros como enlaces MediaWiki:
  `[[Media:ws-broo-cr2.pdf|{{Pdf}}]] [[Media:Broo-cr2.mid|{{mid}}]]`.
- **Uniforme para todos los tipos** (conteo de `[[Media:…]]` en el chunk): pdf 4.691 · mxl 3.861 ·
  mid 2.047 · capx 486 · sib 409 · xml 4.

**Conclusión**: hay **nombre de fichero para todos los tipos**, pero **no URL absoluta**; la URL es
**derivable de forma uniforme** con la regla MediaWiki (`…/index.php/Special:FilePath/<nombre>`, o la
ruta `/images/<hash>/<nombre>`), **no** por reglas distintas por tipo.

Por tanto, los `NULL` de `url`/`file_id` en CPDL son **materialización incompleta del importador**
(la URL se puede derivar), **no** una característica legítima del modelo. El "pendiente" se divide en:
- **(a) exponer enlace externo** derivando la URL → barato y determinista (requiere verificar que
  `Special:FilePath` resuelve y URL-encodear nombres con espacios/paréntesis).
- **(b) rehostear/descargar** los ficheros → **eso sí** depende de la licencia por edición.

## Decisión
> Se mantiene el **cierre estructural** del bloque (sin transformar datos ahora), con el encuadre
> corregido: los 217.343 recursos CPDL son **inventario materializable por derivación de URL**
> (opción a); el rehosting/licencia queda como decisión posterior (opción b).

### Activado (2026-09-19)
Opción (a) **aplicada**: `scripts/apply_cpdl_urls.py` → `works_resources_url` =
`…/Special:FilePath/<nombre URL-encoded>` para **217.343** recursos CPDL, con historial en
`works_resources_field_history` (`operation='derive_url'`). Ciclo probado: apply → verify →
revert → verify → re-apply → verify (217.343 → 0 → 217.343). No se tocó `file_id` ni se descargó
nada. **Nota**: los enlaces externos apuntan a CPDL; su resolución no pudo validarse por
automatización (Cloudflare), se confirmó manualmente por el revisor.

## Estado de módulos
| Módulo | Estado |
|---|---|
| `persons` | ✅ Cerrado |
| `works` | ✅ Cerrado |
| `representations` / `resources` | ✅ **Cerrado sin transformación** |
| Materialización CPDL | ⏸️ Decisión posterior |

No reabrir estos módulos salvo inconsistencia concreta.
