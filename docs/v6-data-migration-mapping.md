# V6 — inventario de migración de datos y propiedad editorial

> **Estado:** inventario técnico inicial, contrastado con migraciones y código versionados; no es todavía el mapeo final validado contra un snapshot real.  
> **Fecha:** 2026-10-31.  
> **Origen principal:** esquema actual de AI_osap-storage en `main`, migraciones `infrastructure/db/migrations_v1`, `infrastructure/db/migrations` y scripts históricos de creación de Resources.  
> **Destino:** modelo V6 `Work → Resource → File`, más propiedad editorial, espacio personal y aportaciones.  
> **No se han consultado bases de datos ni se ha ejecutado ninguna transformación. No se han modificado objetos Cloudflare R2.**

## 1. Decisiones que condicionan el inventario

### 1.1 Modelo de catálogo y almacenamiento

- Work → Resource → File, sin Representation, Blob, StorageLocation ni StorageProvider como entidades del modelo V6.
- Resource pertenece directamente a Work.
- Resource admite cero, uno o varios Files.
- Cada File pertenece a un solo Resource.
- La referencia física existente de R2 se conserva literalmente en File; solo se mueve el dato de referencia dentro de la base de datos.
- No se hace ninguna operación de escritura, copia, borrado, renombrado ni movimiento en R2.
- SHA-256 es integridad, nunca identidad ni deduplicación.
- Los IDs antiguos deben conservarse cuando sea posible y seguro; cualquier cambio exige tabla de correspondencia.

### 1.2 Propiedad editorial y modificación

La regla de propiedad editorial es vinculante:

1. Solo el usuario que aportó originalmente una Work puede modificar esa Work.
2. Si otro usuario inicia una modificación de una Work ajena, se crea automáticamente una Work derivada independiente dentro de su área personal y privada.
3. La Work original no se modifica.
4. El usuario que crea esa versión derivada recibe el crédito de **arreglista** (rol canónico arranger, ID 3, si la vinculación usuario↔persona está resuelta).
5. La Work derivada mantiene una referencia de linaje a la Work original, pero no comparte su identidad ni se publica.
6. Añadir una Work a la biblioteca personal sin modificarla no crea copia.
7. La Work derivada solo pasa al catálogo público mediante una aportación/publicación separada, respetando licencias y trazabilidad.

La especificación funcional está en [v6-user-workspace-contributions.md](v6-user-workspace-contributions.md).

## 2. Inventario de tablas de origen y destino

Las tablas que aparecen a continuación se han observado en los archivos de migración y/o código citados. El destino describe el tratamiento previsto, no afirma que el DDL V6 ya esté creado.

| Tabla de origen | Campos/relaciones relevantes observados | Destino V6 | Regla de transformación |
|---|---|---|---|
| `works` | `id`, títulos, `works_attr_type`, `works_attribution_note`, opus/catálogo, año/época, descripción y otros campos históricos | Work | Mapear identidad y autoría de la obra. No trasladar a Work procedencia, aportante, licencia ni titularidad. Los campos históricos mezclados (`works_origin`, `works_origin_id`, `works_license`, `works_public_domain`, campos de archivo/recurso) se asignan a Resource solo si su relación es demostrable; en caso contrario se dejan sin asignar y se informan como conflicto. |
| `representations` | `id`, `representations_works_id`, `representations_origin`, `representations_origin_id`, `representations_origin_cpdlno`, `representations_type`, `representations_source_name`, `representations_license`, timestamps | Resource | Crear Resource hijo de Work. La procedencia/aportante y licencia pertenecen a este Resource. No trasladar datos si no se puede demostrar a qué material corresponden; no crear campos extra para conservar variantes sin uso. La tabla no se conserva en V6. |
| `representation_persons` | representation_id, person_id, role_id, name | Créditos de Resource | Migrar personas/roles como créditos del Resource, si describen editor/arreglista/adaptador de ese material. No convertir automáticamente todos en créditos de Work. Conservar nombre declarado cuando no haya persona canónica resuelta. |
| `works_resources` | `id`, representation_id, type, name, relative_path, status, file_id, url, archive_id | Resource/File | La tabla actual mezcla semánticas. Descomponer cada fila: identidad del material y procedencia/derechos demostrables pasan a Resource; cada fichero real pasa a File; URL externa permanece en Resource como referencia externa. No asumir que una fila = un File ni añadir metadatos no disponibles. |
| `files` | `id`, `sha256`, `name`, `mime_type`, `size_bytes`, `status`, timestamps | File | Preservar ID si no colisiona; SHA nullable/no único como integridad; conservar nombre/MIME/tamaño/estado. Añadir puntero físico directo, copiado de la fuente autoritativa de R2. |
| `storage_locations` | `id`, `file_id`, `provider_id`, `object_key`, `status` | Campo físico de File + informe histórico | Resolver la clave efectiva exacta del objeto R2, considerando configuración/prefijo. Copiarla literalmente al File. No migrar tabla. |
| `storage_providers` | `id`, `name`, `provider_type`, `config`, `enabled` | Configuración interna de Storage, fuera del catálogo | Usar para interpretar el backend y resolver bucket/prefijo actuales. No copiar como entidad de catálogo. No publicar configuración/secrets. |
| `archives` | `id`, `provider_id`, `name`, `url`, `format`, `local_path`, `status`, `size`, `sha256`, `downloaded_at` | Inventario/procedencia operativa | No convertir Archive en Work ni Resource. Conservar solo datos necesarios para trazabilidad, importación o diagnóstico. Revisar si hay procesos V6 que aún necesiten el registro. |
| `archive_entries` | `id`, `archive_id`, `logical_id`, `composer`, `title`, `work_id`, `relative_path`, `file_id`, `size`, `offset_bytes`, `status` | Trazabilidad de importación y correspondencia File | No asumir que relative_path es clave R2. Conservar vínculo a Work/File solo si el proceso de adquisición/archivo sigue siendo necesario. Offset solo tiene sentido para archivos empaquetados. |
| `download_jobs` | `id`, `file_id`, `provider_id`, `source_url`, `status`, `error_message`, timestamps | Estado operativo de adquisición | Mantener solo si V6 conserva jobs de descarga. Sustituir provider_id por identificador/configuración interna del adaptador, no por entidad de dominio. Revisar referencias a Files fallidos o transitorios. |
| `import_sources` | provider, version, csv_path, notes, imported_at | Auditoría de importación | Conservar como procedencia de lotes si sigue siendo útil. No confundir fuente del lote con origen individual del Resource. |
| `statistics`, `statistics_runs`, `work_statistics` | contadores y ejecuciones; work_statistics tiene FK a Work | Proyecciones/estadísticas | Determinar cuáles se reconstruyen y cuáles son históricos. No copiar métricas derivables sin reconciliarlas; preservar historial de ejecuciones si se necesita auditoría. |
| `votes` | `user_id`, `work_id`, valor/fecha según DDL | Votos sobre Work | Conservar si sigue activa la votación. No interpretar `votes.user_id` automáticamente como identidad de usuario autenticado/propietario de Work; validar su origen y formato. |
| `persons` | `persons_id` UUID, nombre y metadatos de autoridad | Person | Conservar IDs y datos canónicos. La identidad musical Person no es necesariamente la cuenta autenticada User. |
| `persons_aliases` | `person_id`, alias | PersonAlias | Conservar relación y texto, sin fusionar alias con cuentas de usuario. |
| `persons_identity`, `persons_identifiers`, `persons_evidence`, `persons_merge_history`, `persons_authority*` | identidad, identificadores, evidencias, fusiones y autoridad | Identidad/personas y auditoría | Conservar estado vigente e historial necesario. Revisar migraciones posteriores que hayan eliminado/reemplazado tablas antiguas; la copia se hace desde el esquema efectivo, no sumando variantes históricas. |
| `roles` | `id`, `role_name`, descripción | Role | Conservar vocabulario e IDs semánticos. Arreglista corresponde al rol canónico ID 3 según el catálogo actual; validar en snapshot final. |
| `works_person_roles` | work_id, person_id, role_id, order | WorkCredit | Conservar créditos de la obra. Añadir crédito de arreglista a la Work derivada privada, no a la Work original. |
| `works_person_import` | nombre, rol, fuente, resolved | Staging/auditoría de resolución | Conservar si hay propuestas pendientes o historial útil; no duplicar créditos ya materializados en works_person_roles. |
| `work_genres`, `work_instruments`, `work_language`, `work_parts`, `work_tag`, `work_voices`, `work_ensembles` | relaciones de clasificación/partes/plantilla musical | Work y sus relaciones normalizadas | Conservar cardinalidad, cantidades, orden y contexto. No mover a Resource salvo que el dato describa exclusivamente una realización concreta y haya evidencia para hacerlo. |
| `genres`, `instruments`, `languages`, `voices`, `ensembles`, `ensemble_voices`, `epochs`, `tag_work`, `catalog` | vocabularios/catálogos | Catálogos de dominio | Conservar IDs y relaciones. Revisar seeds frente a datos productivos y evitar duplicar catálogos por una carga de semillas. |
| `authority_sync_state` | source, last_packet, last_success_at, last_error, metadata_json | Estado de sincronización | Conservar solo si los procesos V6 mantienen la misma semántica; no copiar cursores incompatibles. |
| `review_items`, `review_decisions` y tablas de auditoría asociadas | item_key, item_type, decisiones y referencias | Revisión/auditoría | Conservar historial si la semántica y las claves siguen siendo válidas. Adaptar referencias a entidades retiradas; no borrar auditoría ni inventar correspondencias. |

### 2.1 Tablas/objetos que NO son origen de cuentas de usuario

El inventario visible de Storage no demuestra que exista una tabla autoritativa de usuarios autenticados. En particular:
- `persons` es identidad de personas musicales;
- `votes.user_id` es un identificador usado por el sistema de votos, no prueba suficiente de una cuenta autenticada;
- `representation_persons` son créditos de una realización;
- `works_origin` puede contener un proveedor o un email según comentario de esquema, pero no es un vínculo fiable de propiedad editorial.

Por tanto, **no se puede inferir quién subió originalmente cada Work a partir de esos campos**. El inventario de usuarios, sesiones, roles y vínculos de identidad debe realizarse en AI_osap-auth / AI_GAMEPC2 y en las fuentes reales de ingestión. Las Works históricas sin evidencia quedan con propiedad editorial no resuelta; no se asignan al usuario actual ni al último editor.

## 3. Descomposición de works_resources

La migración actual creó `works_resources` con una fila por registro asociado a Representation y columnas mezcladas. La transformación V6 debe clasificar cada fila:

| Campo antiguo | Interpretación candidata | Destino V6 | Validación necesaria |
|---|---|---|---|
| `id` | Identidad de fila de recurso antiguo | Resource ID, si la fila representa un material identificable | Confirmar cardinalidad y ausencia de duplicados semánticos |
| `works_resources_representation_id` | Relación con realización antigua | Resource → Work mediante la Work de la Representation | Debe existir Representation y Work destino |
| `works_resources_type` | Tipo/formato/función (semántica aún no cerrada) | Resource.kind o File.format según vocabulario real | Inspeccionar valores reales; no mapear a ciegas |
| `works_resources_name` | Nombre descriptivo o nombre de fichero | Resource.title/name o File.name | Contrastar con files.name y archive_entries |
| `works_resources_relative_path` | Ruta relativa de archivo/mirror | Dato de importación/procedencia, nunca clave R2 por defecto | Identificar consumidor y semántica de ruta |
| `works_resources_status` | Estado de materialización/descarga | Estado de Resource o estado operativo de File | Definir vocabulario y transiciones |
| `works_resources_file_id` | FK a File físico | Resource 1:N File | Revisar referencias compartidas y nulos |
| `works_resources_url` | URL externa | Resource.external_url/source_url | Clasificar página, descarga directa o referencia externa |
| `works_resources_archive_id` | Archive de adquisición | Procedencia/job/archive auxiliar | No convertir Archive en Resource |

Regla: una fila que solo referencia una URL puede producir Resource sin File. Si un Resource tiene varios Files, se crean varios Files relacionados con ese Resource, sin deduplicar por SHA.

## 4. R2: resolución del puntero físico

La migración debe establecer una única fuente de verdad por File. El esquema antiguo observado incluye:
- `storage_locations.object_key`;
- `storage_locations.provider_id`;
- `storage_providers.config` (JSON);
- configuración del adaptador Cloudflare R2, incluida posible `path_prefix`;
- `works_resources_relative_path`;
- `archive_entries.relative_path`;
- `files.sha256` y `File.storage_key()` en el código antiguo.

No se puede dar por sentado que todas esas rutas significan lo mismo. El adaptador actual puede combinar un prefijo de configuración con object_key. El transformador debe obtener la clave efectiva que usa realmente el cliente R2 y almacenarla literalmente en File V6, sin doble prefijo. Si no se puede resolver sin ambigüedad, el registro queda en conflicto y no se inventa una clave.

**Prohibido durante la migración:** PutObject, CopyObject, DeleteObject, upload, rename, cambio de bucket/prefix, derivación de clave desde hash.

## 5. Propiedad editorial y derivación privada: datos nuevos requeridos

El esquema antiguo de Storage inspeccionado no contiene un campo fiable y universal que identifique al usuario que aportó originalmente cada Work. Por ello, V6 necesita representar explícitamente:

| Dato lógico | Uso | Regla |
|---|---|---|
| `created_by_user_id` / `original_contributor_user_id` | Usuario aportante original | Identificador estable de la cuenta autenticada; no usar email como PK |
| `editorial_owner_user_id` | Quién puede modificar esa Work | Para Work aportada, igual al aportante original; para copia derivada, el usuario que la creó |
| `visibility` | public/private/pending u otro enum definido | La copia derivada nace privada; nunca hereda visibilidad pública automáticamente |
| `derived_from_work_id` | Linaje de Work derivada | FK a Work original; no sustituye identidad propia |
| `derivation_type` | Tipo de copia (arreglo/adaptación/edición u otro) | Vocabulario explícito; el usuario recibe crédito de arreglista según regla definida |
| `created_in_workspace_user_id` | Área personal donde se creó | Debe coincidir con usuario autenticado que inicia la derivación |
| `published_at`, `published_by` | Publicación aprobada | Solo se completa al terminar publicación |
| `contribution_id` / relación de auditoría | Expediente que promovió la copia | Mantener vínculo de procedencia y revisión |

No se fija aún si estos campos viven directamente en Work o en tablas de ownership/lineage. El diseño debe permitir más de un tipo de contribución sin convertir Work en un objeto ambiguo. El vínculo a User debe usar la clave primaria real del sistema de autenticación, que está pendiente de inspección.

### 5.1 Diferencia entre Work añadida y Work derivada

- **Work añadida:** tabla/relación personal `workspace_works(user_id, work_id, added_at, personal_state, notes...)`; no crea Work ni Resource.
- **Work derivada:** crea una nueva Work privada y sus Resources/Files propios; guarda `derived_from_work_id`; asigna propiedad editorial al usuario y crédito de arreglista. La original permanece intacta.
- **Work propia:** solo su aportante original puede editarla directamente. Cualquier otro usuario debe derivar copia privada.

La copia debe conservar los datos necesarios para identificar el material de origen y la atribución original, pero no debe compartir File físico con la Work original: los Files de la Work derivada son propios. Si se necesita reutilizar contenido binario, eso exige un objeto físico independiente o un flujo de copia aprobado fuera del corte V6; nunca se comparte una fila File entre Resources. La migración de V6 no toca los objetos R2 existentes.

## 6. Inventario de migración de usuarios y aportaciones

Estas entidades son nuevas en V6; no se deben presentar como tablas antiguas existentes:

| Entidad lógica candidata | Contenido mínimo | Origen | Tratamiento |
|---|---|---|---|
| WorkspaceWork | user_id, work_id, fecha, estado personal, notas/etiquetas privadas | No identificado en Storage | Crear esquema V6; no migrar automáticamente salvo que exista fuente fiable |
| WorkOwnership | work_id, original_contributor_user_id, editorial_owner_user_id, fecha/evidencia | Auth/OSAP/ingestión | Reconstruir desde evidencia real; no inferir desde email/origin/vote |
| WorkLineage | derived_work_id, source_work_id, derivation_type, created_by_user_id | Nueva funcionalidad | Crear solo para copias derivadas; conservar linaje sin modificar original |
| Contribution | aportante, tipo, estado, fecha, versión | No identificado como modelo equivalente en Storage | Nuevo flujo V6 |
| ContributionVersion | snapshot lógico sometido, versión, fecha | No identificado | Congelar lo revisado sin copiar binarios innecesariamente |
| ContributionReview | revisor, decisión, comentario, fecha | Revisión existente puede ser reutilizable tras auditoría | Mapear solo si semántica/refs coinciden; si no, crear historial V6 separado |
| WorkspaceDraft | Work/Resource propuesto privado | No identificado | Crear nuevo; no indexar públicamente |
| UserPersonLink | user_id ↔ persons_id | Auth + autoridad de personas | Relación explícita y validada; una cuenta y una identidad musical son conceptos distintos |

## 7. Conflictos que el transformador debe detectar

1. Representation huérfana o con Work inexistente.
2. Resource antiguo con Representation inexistente.
3. File_id que no existe o aparece relacionado con Resources distintos.
4. Varias StorageLocations para un File, ninguna marcada como válida o más de una R2 plausible.
5. object_key nulo/vacío o discrepancia entre object_key, prefix y configuración del adaptador.
6. Clave R2 repetida por Files diferentes.
7. Hash duplicado: permitido; no fusionar Files.
8. URL externa mezclada con File local en una misma fila.
9. tipo/name/relative_path con semántica incompatible.
10. Licencia de Work frente a licencia de Representation/Resource contradictoria.
11. créditos de Representation sin persona canónica resuelta.
12. referencias de audit/review a IDs retirados.
13. Work histórica sin propietario original verificable.
14. Work con posible procedencia de usuario pero sin cuenta autenticada asociable.
15. Work derivada sin linaje o sin arreglista asociado.
16. duplicados de Work por coincidencia de título/compositor: generar candidatos, no fusionar automáticamente.

Los conflictos se exportan a un informe revisable con tabla, ID antiguo, campos implicados, clasificación, evidencia y decisión pendiente. No se corrigen por heurística silenciosa.

## 8. Validaciones y consultas que debe producir el transformador

Por cada ejecución de `storage_old → storage_new`:

- recuentos por tabla origen/destino;
- IDs preservados, nuevos y sin correspondencia;
- Works/Resources/Files huérfanos;
- cardinalidad Work→Resource y Resource→File;
- Resources sin File y URL-only;
- Files con puntero R2 válido, ausente o conflictivo;
- comparación literal de cada puntero fuente/destino;
- duplicados de SHA sin fusión;
- referencias compartidas de File detectadas;
- relaciones de personas/roles y créditos arreglista;
- obras sin propietario editorial conocido;
- relaciones WorkspaceWork sin duplicados;
- Work derivadas con linaje y visibilidad privada;
- expedientes de aportación y referencias auditables;
- restricciones FK, índices y unicidad;
- consultas de muestra y pruebas de descarga autenticada.

El transformador debe ser repetible: reconstruir storage_new desde cero en cada iteración. No se ejecuta contra producción hasta tener snapshot final congelado, revisión y autorización explícita.

## 9. Fuentes de esquema y límites comprobados

- [DDL antiguo de Files, StorageLocations, StorageProviders y DownloadJobs](https://github.com/recursosformacion/AI_osap-storage/blob/main/infrastructure/db/migrations_v1/001_init.sql)
- [DDL de Archives y ArchiveEntries](https://github.com/recursosformacion/AI_osap-storage/blob/main/infrastructure/db/migrations_v1/002_archives.sql)
- [DDL de import_sources y statistics](https://github.com/recursosformacion/AI_osap-storage/blob/main/infrastructure/db/migrations_v1/003_import_sources_statistics.sql)
- [DDL histórico de Work](https://github.com/recursosformacion/AI_osap-storage/blob/main/infrastructure/db/migrations_v1/007_works.sql)
- [DDL baseline actual versionado](https://github.com/recursosformacion/AI_osap-storage/blob/main/infrastructure/db/migrations/001_baseline_schema.sql)
- [Creación histórica de Representation, works_resources y representation_persons](https://github.com/recursosformacion/AI_osap-storage/blob/main/scripts/migrate_representations_resources.sql)
- [Entidad y repositorio actuales de Representation/Resource](https://github.com/recursosformacion/AI_osap-storage/blob/main/domain/entities/representation.py)
- [Resolución actual de File.storage_key desde SHA](https://github.com/recursosformacion/AI_osap-storage/blob/main/domain/entities/file.py)

**Límite de precisión:** las migraciones versionadas muestran la historia del esquema, pero no prueban que el esquema productivo actual sea idéntico al último DDL versionado. Antes de fijar el mapeo campo a campo definitivo hay que obtener un snapshot de solo lectura y extraer SHOW CREATE TABLE, índices, constraints, triggers, vistas, recuentos y valores distintos de las columnas ambiguas. Este documento marca expresamente las ambigüedades; no las rellena por inferencia.

## 10. Siguiente bloque de auditoría

1. Inspeccionar auth y OSAP-API para localizar PK de User, roles/scopes y vínculo User↔Person.
2. Inspeccionar todos los consumidores de Work/Resource/File y el adaptador R2 para determinar la clave efectiva.
3. Obtener inventario DDL real de snapshot `storage_old`.
4. Extraer distribución de valores de `works_resources_type/status`, `representations_type/origin/license`, `storage_locations.status` y `storage_providers.config` (sin exponer secretos).
5. Cerrar reglas de propiedad para las Works históricas.
6. Diseñar DDL V6 y transformador con informe de conflictos.
7. Probar en `storage_new`; nunca modificar `storage_old` ni objetos R2.

## 2.3 Decisión vinculante: autoría en Work; procedencia y derechos en Resource

Esta distribución sustituye cualquier mapeo anterior que colocara procedencia o licencia en Work:

- **Work contiene la autoría de la obra.** Todos los Resources de una misma Work comparten esa autoría. Si dos materiales tienen compositores incompatibles porque representan obras intelectualmente distintas, no se deben forzar bajo una misma Work. Se admiten coautores reales. Los estados de atribución distinguen compositor identificado, anónimo declarado, tradicional y desconocido/no resuelto; no se crean personas ficticias para los tres últimos casos.
- **Resource contiene la procedencia/aportante.** Puede ser una fuente externa (PDMX, IMSLP, CPDL) o el usuario que incorpora directamente ese Resource. Para un alta autenticada, el usuario aportante se toma de la identidad validada por el servidor, sin preguntar ni aceptar una identidad enviada por el navegador.
- **Resource contiene los derechos/licencia aplicables a ese material**, cuando se conocen. El titular puede ser el compositor o un tercero. No se deduce del compositor ni del aportante, y no se replica a todos los Resources de la Work.
- **No acumular datos hipotéticos.** No crear una estructura de derechos compleja, tablas de evidencias, historiales, campos de titular o fuentes alternativos si no hay un uso real y datos disponibles. Guardar lo mínimo necesario y fiable. Si un dato no se conoce, dejarlo sin determinar; no inferir ni completar por defecto.

Regla de migración: `works_origin`, `works_origin_id`, `works_license` y `works_public_domain` no son atributos V6 de Work. Solo se trasladan a un Resource cuando el registro antiguo permite asociarlos inequívocamente con ese Resource. Si no, se registra el conflicto y no se asigna por heurística. La autoría histórica de Work no se modifica por diferencias de procedencia/licencia entre Resources.
