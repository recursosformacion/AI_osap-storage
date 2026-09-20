# Corrección — root del proveedor de almacenamiento (2026-09-20)

## 1. Síntoma detectado

El corpus PDMX está rehospedado en disco (**254.035** `.mxl`, **1,85 GB** en
`G:\osap-storage\mxl`), con su registro en `files` (254.035) y `storage_locations`
(254.035, `status='stored'`), pero el proveedor `local` resolvía a una ruta inexistente.

| Elemento | Valor encontrado |
|---|---|
| `storage_providers` id=1 | `name='local'`, `provider_type='local_disk'`, `config={"root": "G:/osap-storage/files"}` |
| `G:\osap-storage\files` | **no existe** |
| `object_key` (muestra) | `./mxl/1/11/Qmbb…mxl` |
| `config.yaml` `repository.local.root` | `D:/Proyectos/AI_OSAP/osap-storage/devdata` (solo **100** `.mxl` de muestra) |

## 2. Diagnóstico (read-only)

`LocalDiskBackend` resuelve `root / object_key` (`infrastructure/providers/local_disk.py:25,33,41`).

Muestra aleatoria de **4.000** `storage_locations` (semilla fija):

| root | ficheros existentes |
|---|---|
| `G:/osap-storage/files` (configurado) | **0 / 4.000** |
| `G:/osap-storage` (propuesto) | **4.000 / 4.000** |

Consecuencia real: `GET /api/v1/files/{file_id}/content` (`StreamFile` comprueba existencia
antes de responder, `application/use_cases/stream_file.py:60`) devolvía **404** con el corpus
presente en disco. Ejemplo: `file_id=624` → 404.

**No afectaba** a la descarga pública PDMX vía CDN (`/api/download/{id}` redirige a
`cdn.openmusicrepository.com/...` por `settings.r2_serve_directly`), que seguía sirviendo bytes.

## 3. Corrección aplicada (auditable y reversible)

| Destino | Antes | Después |
|---|---|---|
| `osap-storage.storage_providers` id=1 | `{"root": "G:/osap-storage/files"}` | `{"root": "G:/osap-storage"}` |
| `osap-storage_test.storage_providers` id=1 | `{"root": "G:/osap-storage/files"}` | `{"root": "G:/osap-storage"}` |
| `config.yaml` `repository.local.root` | `D:/Proyectos/AI_OSAP/osap-storage/devdata` | `G:/osap-storage` |

Revert (una fila por BBDD):

```sql
UPDATE storage_providers SET config='{"root": "G:/osap-storage/files"}' WHERE id=1;
```

No se movió ni se copió ningún fichero: el corpus ya estaba correcto; lo incorrecto era la
configuración que lo apuntaba.

## 4. Verificación

Se reinició el servidor (el `StorageBackendRegistry` cachea el backend por
`("id", provider.id)`, `infrastructure/providers/registry.py:39`, así que el proceso antiguo
mantenía el root erróneo).

**Streaming local** — `GET /api/v1/files/{id}/content`:

| file_id | antes | después |
|---|---|---|
| 624 | 404 | **200** (9.006 B) |
| 625 | — | **200** (8.652 B) |
| 100000 | — | **200** (7.962 B) |
| 200000 | — | **200** (17.857 B) |

**Cadena pública** — `GET /api/download/{resource_id}` → 302 → CDN → 200:

| resource | location | follow |
|---|---|---|
| 132369 | `cdn…/storage2017/mxl/9/12/QmRBh…mxl` | **200** (2.889 B) |
| 114374 | `cdn…/storage2017/mxl/12/16/QmUDok…mxl` | **200** (39.411 B) |
| 176079 | `cdn…/storage2017/mxl/8/56/QmQzCX…mxl` | **200** (2.403 B) |

**Suite**: `ruff` limpio · **298 tests** en verde.

## 5. Riesgo operacional anotado

`ensure_default_provider` (`infrastructure/bootstrap.py:32`) **solo crea** el proveedor si no
existe ninguno: no reconcilia `config` cuando la fila ya está creada. Por eso cambiar
`repository.local.root` en `config.yaml` **no** surte efecto sobre una BBDD existente, y el
desajuste pudo pasar inadvertido. Recomendación (no implementada): añadir una comprobación de
salud (`infrastructure/doctor.py`) que valide que el `root` del proveedor existe y que una
muestra de `object_key` resuelve a fichero real.
