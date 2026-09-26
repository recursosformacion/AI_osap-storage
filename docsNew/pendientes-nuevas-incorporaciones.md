# Pendientes y nuevas incorporaciones (2026-09-22)

Registro de deuda abierta y fuentes candidatas, para no perderlas durante el cierre.
Complementa `fork-plan-migracion.md` §5 y `modelo-persona-completo.md` §11.

## Cierre operativo (bloquea "liberar")

1. **Servicios con la BD correcta**: el entorno servido por Apache debe arrancar con
   `OSAP_CONFIG=config.yaml` (BD `osap-storage`), no `config.test.yaml`
   (`osap-storage_test`). El task de VS Code ya está corregido
   (`osap-api/.vscode/tasks.json`).
2. **Procesos duplicados**: hay dos uvicorn por puerto (venv de storage + Python del
   sistema). Dejar uno por puerto; los hijos huérfanos (`spawn_main`) retienen el socket.
3. **Reiniciar `osap-api`** para aplicar `_INDEXED_PROVIDERS` con `cpdl`.
4. **Mojibake residual** en `osap-storage` (nombres visibles: `Ä H ELÇÄOÄLU`,
   `Å uvis`, `Äáong An`). **Comprobado 2026-09-23**: el nombre original en el staging
   (`works_person_import`) está **también corrupto** en 58/59 casos visibles → re-resolver
   no recupera; haría falta **re-importar desde el mirror PDMX/MuseScore** (no presente en
   local: no hay `PDMX.csv`/`metadata/` en `G:\`). Único caso recuperable desde staging:
   `Jiří Antonín Benda`. Nota: `is_mojibake` da **falsos positivos** en portugués/español
   válidos (`João…`, `Estêvão…`, `Canção…`), así que el recuento real es menor que el
   reportado. Se deja como deuda conocida.

## Nuevas incorporaciones (fuentes propuestas)

### RISM — permalink de la ficha
Las fuentes RISM sin copia digitalizada devuelven `links: []` → `view_url=None` → la UI no
ofrece enlace. Propuesta: fallback derivado del `source_id`:
`sources/455010113` → `https://rism.online/sources/455010113` (HTTP 200 verificado).
Punto único: `RismStorageCatalogProvider._to_candidate` (`osap-api`).
RISM es **finding aid** (1.565.667 fuentes, metadata): **no** se indexa.

### Humdrum / Josquin Research Project (candidato a provider)
`https://github.com/josquin-research-project` (Stanford; mantiene Craig Sapp):
- `jrp-scores` — polifonía vocal **1420–1520** en **Humdrum (`.krn`)**.
- `Mou` — música de Jean Mouton en Humdrum.

Valor: corpus codificado (análisis), dominio público por época, cubre un periodo débil en
OMR/PDMX; solapa parcialmente con CPDL (Josquin/Mouton) pero aporta la versión de
referencia. Coste: requiere conversor **`.krn` → MusicXML/MEI** (Verovio humdrum / humlib);
corpus de miles, no masivo → provider **dirigido**, no ingesta.
**Pendiente antes de decidir**: verificar LICENSE por repo y tamaño real de `jrp-scores`.

## Deuda de contenido detectada hoy

| # | Tema | Detalle |
|---|---|---|
| 1 | ~~Importador CPDL pierde multi-voicing~~ | **Resuelto 2026-09-23**: `_tmpl_multi` usa `re.findall` → captura todas las plantillas `{{Voicing}}`; el importador escribe `voicings`+`work_voicing`. |
| 2 | ~~723 obras CPDL sin voicing indexable~~ | **Resuelto 2026-09-23**: `is_useful_term`/`normalize_term` quitan el conteo inicial; «4 equal voices» → `EQUAL VOICES`. Re-derivar con `backfill_work_voicings.py` + reindexar `--providers cpdl`. |
| 3 | ~~`cpdl_voicings` inexistente~~ | **Resuelto 2026-09-23**: tabla legada retirada; el par `voicings`+`work_voicing` (migración `007_voicings`) la sustituye. `backfill_cpdl_voicings.py` eliminado. |
| 4 | 241 obras CPDL sin `cpdl_editions` | Sin edición en origen → sin `representation` |
| 5 | 2.591 fusiones del índice sin compositor | `_ingest` empareja por `title_key` cuando no hay compositor (riesgo de conflación) |
| 6 | 24 avisos `ruff` preexistentes | Ficheros fuera de los modificados en el cierre |
| 7 | `_review_page` con tope 8×500 | Filtra en memoria; `total=None` (ya documentado); >4.000 filas no paginables |
| 8 | ~~`voicings` solapa con `ensembles`~~ | **Resuelto 2026-09-23**: fusión en `ensembles`/`work_ensembles` (+`ensemble_voices`), `ensembles_code` en MAYÚSCULAS, `voicings`/`work_voicing` eliminadas (migración `008`). |
| 9 | Sin fechas para `epoch` / enriquecimiento por internet | `works.works_year` está **100 % vacío** (310.455 obras) y `persons` **no tiene** columna `*_epoch_id`; solo 171 `persons_birth_year` / 129 `persons_death_year`. Sin fecha ni identificador externo (`works_origin_id` es id de página CPDL/PDMX), el enriquecimiento por internet no es validable automáticamente. No se han hecho escrituras masivas desde fuentes no validadas. Propuesta: definir fuente + columnas de procedencia/confianza y ejecutar en `--dry-run` primero. |

## Hecho el 2026-09-22 (contexto)

- **CPDL indexado**: `_iter_cpdl` en `script/index_works.py` (compositor desde
  `works_person_roles` rol 1 = persona propia de CPDL, **sin re-resolver por nombre**;
  representaciones desde `works_resources`; voicing crudo + canónico).
  Resultado: **99.134 representaciones**, `index_works` +217, `index_work_voicings`
  (60.790 crudos + 94.512 canónicos).
- **`cpdl` en `_INDEXED_PROVIDERS`** → el orquestador sirve CPDL del índice y omite el
  provider vivo en el search genérico (sin duplicados). `/api/v1/cpdl/*` intacto.
- **Voicing**: tabla satélite `index_work_voicings(work_id, kind, term)`;
  `kind='cpdl'` (términos crudos) y `kind='canonical'` (`ensembles_code`).
