# Diagnóstico — Representaciones y Recursos (2026-09-19)

Read-only. Estado actual del bloque tras op2. No se ha modificado nada.

## 1. Tablas del bloque
`representations`, `representation_persons`, `works_resources` (canónicas) · `files`,
`storage_locations`, `archives` (almacenamiento) · `archive_entries`, `cpdl_editions`,
`cpdl_edition_files`, `cpdl_edition_persons` (legado/staging).

## 2. Relaciones (FKs reales)
```
works ── representations (representations_works_id)
          ├── representation_persons (…_representation_id → representations; …_person_id → persons)
          └── works_resources (works_resources_representation_id)   [nullable]
works ── works_resources (works_resources_work_id)                  [siempre]
works_resources ── files (…_file_id) · archives (…_archive_id)
```

## 3. Qué es una representación CPDL hoy
- **81.983** representaciones, **todas** `origin='cpdl'`, `type='edition'`,
  `origin_id = página:cpdlno` (p. ej. `4560:3763`), `license` por edición.
- **80.166** editores en `representation_persons` (rol 6).
- `source_name` es `NULL` en CPDL (solo se usó en PDMX, ya disuelto en op2).

## 4. Los 471.378 recursos
| | |
|---|---|
| Sin representación (PDMX, directos a `work`) | **254.035** |
| Con representación (CPDL) | **217.343** |
| Con `file_id` (internos, descargables) | 254.035 (solo PDMX) |
| Con `url` externa | **0** |
| Obras con recursos | 303.923 (de 310.455) |
| Tipos | MXL 314.983 · PDF 75.250 · MIDI 44.850 · MP3 10.267 · CAPX 9.030 · MUS 8.465 · SIB 6.399 · MSCZ 2.115 |
| Recursos por representación | min 0 · máx 225 · media 2,65 |
| Representaciones **sin recursos** | **11.242** |
| Duplicados `file_id` | 0 |
| Duplicados `(representación, nombre, tipo)` | 0 |

Interpretación: los recursos PDMX son **1:1 con `files`** y cuelgan directamente de la obra (op2);
los CPDL cuelgan de su edición (2,65 ficheros/edición) pero **no tienen `file_id` ni `url`** →
**no descargables** (materialización pendiente).

## 5. Consumidores actuales
- **representations / works_resources**: `SqlRepresentationRepository`, `SqlResolutionSource`
  (resolver), `GetWork`/`SearchWorksFull`, provider `_representations`/`_resources`, ruta de descarga,
  whitelist del CRUD.
- **archive_entries** (legado): `SqlArchiveEntryRepository`, `import_pdmx`, y **fallback** de `GetWork`
  y de la descarga.
- Modelo vigente: **op2** (representaciones solo CPDL; recursos PDMX directos al `work`).

## 6. Canónico vs legado
| Nivel | Canónico | Legado |
|---|---|---|
| Obra | `works` | `archive_entries` (PDMX) |
| Representación | `representations` + `representation_persons` (CPDL) | `cpdl_editions` + `cpdl_edition_persons` |
| Recurso | `works_resources` (con `work_id`; `representation_id` opcional) | `cpdl_edition_files`, `archive_entries` |

## 7. Cadena obra → representación → recurso (estado)
- **PDMX**: `work → resource` (1:1; sin nivel de representación — decisión op2).
- **CPDL**: `work → representation (edición) → N resources` (inventario; **sin fichero**).
- No hay transformación pendiente: la estructura es coherente y sin duplicados.

## 8. Qué falta para producción
1. **Materialización CPDL** (217.343 recursos sin `file_id`/`url`) → decisión aparte (URL externa vs
   descarga propia), por licencia de edición.
2. **11.242 representaciones sin recurso** → conservadas como inventario (decisión §11).
3. No hay otra transformación estructural necesaria en este bloque.
