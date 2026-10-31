# OSAP Storage V6 — reconstrucción, API, índice e implantación

> **Estado:** documento de diseño y auditoría previa a implementación.  
> **Fecha de revisión:** 2026-10-30.  
> **Repositorios revisados:** `recursosformacion/AI_osap-storage` y `recursosformacion/AI_GAMEPC2`, rama `main`.  
> **Alcance:** modelo de datos V6, conservación de objetos Cloudflare R2, reconstrucción de la base de datos, API consumida por OSAP, reconstrucción/sincronización del índice y despliegue coordinado.  
> **Importante:** este documento no ejecuta migraciones, no modifica bases de datos, no toca objetos R2 y no cambia código de producción.

## 1. Objetivo y decisiones vinculantes

V6 es una sustitución completa del modelo anterior. No es una migración gradual y no debe mantener dos modelos activos ni una capa permanente de compatibilidad.

El modelo de catálogo y almacenamiento queda reducido a:

`Work → Resource → File`

- **Work** representa la obra musical como entidad catalográfica.
- **Resource** representa una realización o material musical concreto de esa obra: partitura, grabación, arreglo, edición, transcripción, interpretación u otro material identificable. Sus características y procedencia pertenecen al propio Resource cuando describen ese material.
- **File** representa un objeto digital físico concreto, con su formato, nombre, MIME, tamaño, estado e identificador físico opaco.

Decisiones que no deben reabrirse accidentalmente:

1. `Representation` desaparece del modelo V6. No habrá tabla, entidad, DTO ni dependencia de dominio con ese nombre.
2. `Blob` no existe en V6.
3. `StorageLocation` desaparece como entidad y tabla del modelo de catálogo.
4. `StorageProvider` desaparece como entidad y catálogo de dominio. Que Storage use internamente un adaptador de R2 no convierte al proveedor físico en una entidad del catálogo.
5. Resource pertenece directamente a Work.
6. Un Resource puede tener cero, uno o varios Files. Cero Files permite recursos descritos mediante URL externa o recursos todavía no materializados. Varios Files permiten distintos formatos útiles del mismo Resource.
7. Un File físico pertenece a un único Resource. No se comparte el mismo registro File entre Resources distintos.
8. Si otro proveedor aporta un archivo que no se ha verificado como el mismo objeto y la misma realización, se registra como otro Resource y su propio File. No se fusiona por similitud de nombre, tamaño o hash.
9. SHA-256 es una evidencia de integridad, no identidad lógica. No es clave primaria, clave única, mecanismo de deduplicación ni generador de la clave física.
10. Cada File guarda directamente el puntero físico opaco al objeto Cloudflare R2. El puntero no se calcula a partir del hash.
11. Los objetos que ya están en R2 se conservan en su ubicación actual. La migración de V6 recoloca sus referencias en la tabla/campo correspondiente; no mueve, copia, renombra, borra ni vuelve a subir los objetos.
12. La API pública de descarga resuelve siempre `Resource → File → objeto físico`. No expone hashes, claves internas ni detalles del proveedor.
13. El corte será único y coordinado entre la base de datos, osap-storage y OSAP-API. No se reabrirán importadores hasta superar la validación posterior al despliegue.

El documento maestro de decisiones del modelo está en [v6-work-resource-model.md](v6-work-resource-model.md). La decisión de retirar ubicaciones está registrada en [v6-storage-locations-removal.md](v6-storage-locations-removal.md). Este documento añade el impacto operativo e integración que debe resolverse antes de implementar.

## 2. Qué se ha inspeccionado y límites de esta auditoría

Se ha revisado código y documentación versionados en `main` de ambos repositorios, en particular:

### AI_osap-storage

- `infrastructure/db/migrations/001_baseline_schema.sql` y el catálogo de migraciones.
- Entidades `domain/entities/file.py`, `representation.py`, `storage_location.py`, `storage_provider.py`.
- `domain/services/availability.py`.
- `application/services/file_publisher.py` y `mirror_resources.py`.
- Casos de uso de alta, registro, descarga, publicación, verificación y borrado de Files.
- `infrastructure/providers/cloudflare_r2.py`.
- Repositorios SQL de File, Resource/Representation, providers y resolución.
- `api/routes/provider.py`, `api/schemas.py`, `api/dependencies.py`.
- `docs/provider-api-contract.md`, README y documentación histórica de representación/recursos.

### AI_GAMEPC2 (OSAP-API y núcleo)

- `script/rebuild_index.py`.
- `script/index_works.py`.
- `script/resolve_index_composers.py`.
- `script/sync_index.py`.
- `providers/omr/endpoints.yaml` y `mapping.yaml`.
- `src/osap/infrastructure/providers/fetchers/omr_fetcher.py`.
- `src/osap/infrastructure/resources/resource_manager.py`.
- Documentación V6 de Work/Resource y retirada de StorageLocation.

**Límite:** esto es una auditoría documental y de código fuente, no una inspección de la base de datos de producción ni una prueba de llamadas reales contra producción. No se ha consultado ni modificado el contenido actual de R2. Tampoco se ha ejecutado el índice ni una descarga de extremo a extremo. Los puntos que requieren datos de producción o pruebas están marcados como pendientes y no se presentan como verificados.

## 3. Modelo V6 y responsabilidades

### 3.1 Work

Work conserva la identidad y los metadatos de la obra, independientes de una edición o archivo concreto. Debe seguir siendo posible encontrar y describir una obra aunque no tenga ningún Resource descargable.

Como mínimo, la migración debe conservar los datos propios de la identidad de la obra que hoy se encuentran en `works` y sus relaciones: título, subtítulo, autoría/compositoría, catálogo, año/época, descripción y clasificaciones que realmente describan la obra.

La procedencia/aportante, los derechos y la licencia no son atributos de Work: pertenecen a cada Resource. Un identificador externo mínimo de Work puede conservarse únicamente si es necesario para reconciliar la identidad o mantener la idempotencia de una fuente; no representa procedencia ni titularidad.

### 3.2 Resource

Resource es hijo directo de Work. No existe un nivel intermedio.

Resource debe poder describir, según el tipo de material y los datos disponibles:

- clase o naturaleza del material;
- procedencia/aportante del material (PDMX, IMSLP, CPDL o usuario autenticado), cuando se conozca;
- identificador externo o URL de origen, solo si son necesarios para localizar/reconciliar ese Resource;
- derechos y licencia aplicables a ese Resource, cuando se conozcan; el titular puede ser el compositor o un tercero;
- edición, arreglo, transcripción, versión o interpretación, si procede;
- instrumentación, voces/conjunto, idioma, tonalidad u otras características que correspondan al material;
- metadatos editoriales útiles que antes estaban ligados a Representation;
- relación con sus Files.

La lista anterior es un inventario semántico, no una declaración de que todos esos campos deban ser columnas escalares. El diseño físico definitivo debe revisar cardinalidades, vocabularios y datos reales antes de fijar el DDL.

Resource puede existir sin File. La ausencia de File no significa que Resource sea inválido: puede tratarse de un enlace externo, de un material inventariado aún no descargado o de una referencia cuya materialización está pendiente.

### 3.3 File

File representa un objeto físico independiente. Debe guardar un identificador opaco de objeto (por ejemplo, la clave existente de R2), nombre, MIME, tamaño, formato si se decide almacenarlo explícitamente, estado operativo, SHA-256 opcional como dato de integridad y marcas temporales.

La clave física:
- se copia literalmente desde la referencia válida existente;
- no se deriva de SHA-256;
- no se reconstruye por convención;
- no se normaliza ni se cambia de prefijo durante la migración;
- no se interpreta como ruta lógica del catálogo;
- no se expone en DTO públicos.

No debe haber una restricción `UNIQUE(sha256)`. Dos Files distintos pueden tener el mismo hash y seguir siendo dos registros y dos relaciones independientes. No se deduplican durante la reconstrucción.

### 3.4 Multiplicidad y propiedad

- Work 1:N Resource.
- Resource 1:N File.
- File pertenece a un solo Resource.
- Resource 0:N Files.
- Resource puede tener URL externa sin File.
- Cada File es un objeto físico distinto desde el punto de vista del catálogo.

La migración debe detectar los casos antiguos en los que un File parece estar referenciado por más de un Resource. No debe resolverlos automáticamente compartiendo el File. Debe generar un informe de conflicto y crear registros separados solo cuando la evidencia permita reconstruir inequívocamente los objetos físicos; de lo contrario, el caso queda bloqueado para decisión explícita.

## 4. Cloudflare R2: conservación estricta

### 4.1 Qué no se hace

Durante el corte V6 no se debe ejecutar ninguna operación de escritura o mutación de objetos R2:

- no `PutObject`, upload ni copia;
- no `CopyObject`;
- no `DeleteObject`;
- no renombrado lógico mediante copiar/borrar;
- no cambios de bucket, prefijos ni dominio público;
- no recálculo de claves a partir del SHA-256;
- no reconstrucción de las claves por el nombre del archivo.

La operación prevista es exclusivamente una transformación de metadatos en la base de datos.

### 4.2 Qué se hace

1. Leer el puntero actual que identifica cada objeto almacenado. En el esquema actual ese puntero se encuentra asociado a una fila de `storage_locations` (`object_key`) y a un proveedor configurado; el adaptador R2 aplica además el prefijo de configuración al resolver la clave física.
2. Confirmar qué valor es la clave efectiva completa del objeto y qué parte corresponde a `path_prefix`. No se debe concatenar dos veces el prefijo.
3. Determinar el Resource de destino y el File que representa ese objeto.
4. Copiar el valor exacto de la clave efectiva al campo directo del File V6, manteniendo el mismo bucket y configuración R2.
5. Verificar existencia/acceso con una operación de lectura de metadatos (por ejemplo HEAD) y, en las pruebas funcionales, descarga de muestra. Estas comprobaciones no modifican el objeto.
6. Comparar los punteros antes/después para demostrar que no se ha cambiado ninguna clave.

### 4.3 Inventario de referencias

La auditoría debe contemplar, como mínimo:

- `storage_locations.object_key` y `storage_locations.provider_id`;
- configuración R2: bucket, endpoint, `public_url`, `path_prefix`;
- `files.sha256`, nombre, MIME, tamaño y estado;
- `works_resources` y sus relaciones con Work y Representation antiguas;
- `archive_entries.file_id` y `archive_entries.relative_path`;
- rutas históricas de mirror/archive que puedan confundirse con una clave de R2.

No se debe asumir que `archive_entries.relative_path` es siempre la clave R2. El puntero autoritativo debe salir de la referencia que realmente usa el backend en producción. Si hay más de una fuente o contradicciones, deben clasificarse y resolverse antes de cargar V6.

### 4.4 Comprobación de integridad

Por cada File migrado con puntero R2:
- existe exactamente un puntero físico válido;
- el puntero es idéntico al de la fuente autoritativa;
- el objeto existe en el bucket configurado;
- el tamaño, cuando está registrado, no contradice el objeto;
- el SHA-256, si se verifica, coincide con el contenido, sin usarlo para cambiar identidad ni clave;
- el File está vinculado al Resource correcto;
- no existe File huérfano ni puntero duplicado accidentalmente por error de transformación.

La verificación puede generar un informe, pero no debe alterar los objetos ni corregir automáticamente las claves.

## 5. Base de datos: reconstrucción controlada

### 5.1 Bases y propósito

Se propone mantener nombres separados y explícitos:

| Nombre | Uso | Escrituras |
|---|---|---|
| `osap_storage` | Base productiva antigua durante el servicio V5 | Solo hasta el congelamiento acordado |
| `storage_old` | Snapshot descargado de producción para desarrollo y auditoría | Ninguna; lectura |
| `storage_new` | Reconstrucción V6 de desarrollo | Sí, solo durante transformación y pruebas |
| `osap_storage` tras el corte | Base productiva V6 | Solo tras aceptación formal |
| `osap_storage_old` | Respaldo aislado de la base productiva anterior | Ninguna; lectura/rollback |

Los nombres son una propuesta operativa; deben confirmarse con el entorno real antes de ejecutar comandos. No se debe sobrescribir ni renombrar una base real sin un plan de respaldo comprobado.

### 5.2 Ciclo de desarrollo

1. Obtener un snapshot coherente de la base productiva y descargarlo al entorno de desarrollo como `storage_old`.
2. Confirmar que el snapshot se puede restaurar y que las tablas, índices, vistas, triggers y procedimientos necesarios están presentes.
3. Crear `storage_new` desde cero usando el DDL V6, no alterando sucesivamente la copia antigua.
4. Ejecutar un transformador repetible `storage_old → storage_new`.
5. Cada ejecución de desarrollo debe poder reconstruir `storage_new` desde cero, de forma determinista. Corregir una regla de mapeo significa volver a generar la base nueva, no acumular parches manuales.
6. Comparar recuentos, relaciones, punteros y muestras funcionales.
7. Ejecutar osap-storage V6 apuntando exclusivamente a `storage_new`.
8. Ejecutar OSAP-API contra la instancia V6 y la base de índice de pruebas correspondiente.
9. No conectar el código V6 a `osap_storage` productiva durante el desarrollo.

### 5.3 Guardia anti-producción

El arranque de la configuración V6 de desarrollo debe fallar si el nombre de base no es exactamente `storage_new` (o el nombre de pruebas autorizado). La comprobación debe ser explícita y ejecutarse antes de aceptar tráfico o tareas.

La configuración de la aplicación antigua puede leer `storage_old` para comparar resultados, pero no debe escribir en el snapshot.

No se aceptan valores por defecto silenciosos que puedan conectar el código V6 a producción.

### 5.4 Congelamiento y corte

Antes del corte:
- suspender importadores de IMSLP, CPDL y cualquier otra fuente que escriba en osap-storage;
- suspender sincronizaciones de autoridad, tareas programadas, jobs de descarga/materialización, paneles de administración y operaciones manuales de escritura;
- suspender las tareas de sincronización/reconstrucción de índice que lean el origen durante el snapshot, o coordinarlas para que trabajen sobre una instantánea fija;
- confirmar que no quedan transacciones ni procesos de escritura;
- registrar hora del congelamiento y evidencias de procesos detenidos.

Después:
1. generar snapshot final de la base antigua ya congelada;
2. reconstruir `storage_new` desde ese snapshot final, no desde una copia anterior de desarrollo;
3. ejecutar transformación y validaciones completas;
4. desplegar el servicio osap-storage V6;
5. desplegar/configurar OSAP-API para el contrato V6;
6. reconstruir el índice de OSAP desde fuentes V6 y validar sus consumidores;
7. ejecutar pruebas de humo y aceptación;
8. solo entonces habilitar escrituras, importadores y tareas programadas.

### 5.5 Rollback

Antes de reabrir escrituras V6, rollback significa volver a la versión de servicio y base V5 congeladas. La base antigua debe permanecer aislada, sin sincronización automática con V6.

Una vez que V6 acepte escrituras, volver a V5 sin reconciliación puede perder las nuevas operaciones. Por eso el instante de reapertura es un punto formal de no retorno operativo. Si se necesita rollback después, primero debe diseñarse y aprobarse una reconciliación de las escrituras V6; no se debe simplemente cambiar la conexión de base.

## 6. Inventario de tablas y transformación

El inventario se basa en el esquema y código versionados. Los nombres definitivos del esquema V6 deben cerrarse en el DDL antes de programar la transformación.

### 6.1 Datos que deben conservarse

| Área | Tablas/estructuras antiguas observadas | Tratamiento V6 |
|---|---|---|
| Obras | `works` | Conservar y mapear a Work; preservar IDs cuando sea viable y no genere colisiones |
| Personas | `persons`, `persons_aliases`, `persons_authority*`, `persons_evidence`, `persons_identifiers`, `persons_merge_history` | Conservar; no mezclar con la retirada de Representation |
| Roles y atribución | `roles`, `works_person_roles`, `works_person_import`, historial/auditoría de atribución | Conservar relaciones, roles, orden, fuente y auditoría |
| Clasificación | `genres`, `work_genres`, `instruments`, `work_instruments`, `languages`, `work_language`, `work_parts`, `work_tag`, `tag_work`, `voices`, `work_voices`, `ensembles`, `work_ensembles`, `ensemble_voices` | Conservar, comprobando cardinalidad y normalización |
| Recursos | `works_resources` y campos asociados | Convertir a Resource directo de Work; eliminar referencia a Representation |
| Representaciones | `representations`, `representation_persons`, campos de metadatos/alias de representación | Distribuir la información a Work o Resource según semántica; no conservar entidad intermedia |
| Files | `files` | Convertir a File V6; quitar identidad por SHA única y añadir puntero físico directo |
| Ubicaciones | `storage_locations` | Usar solo como fuente de punteros durante la transformación; no existe en el modelo final |
| Proveedores | `storage_providers` | Usar para identificar la configuración histórica y distinguir backends; no copiar como entidad de catálogo V6 |
| Archivos/mirror | `archives`, `archive_entries` | Conservar solo los datos que sigan siendo necesarios para inventario, procedencia o procesos de importación; no usarlos como sustituto de Resource/File |
| Descargas | `download_jobs` | Revisar y mapear como estado operativo de adquisición; no conservar provider_id como dependencia de entidad de dominio |
| Votación/estadística | `votes`, `statistics`, `work_statistics`, `statistics_runs` | Conservar y validar sus claves de Work/persona/usuario |
| Autoridad y sincronización | `authority_sync_state` | Conservar estado operativo si los procesos siguen activos |
| Catálogos | `catalog` y catálogos auxiliares | Conservar vocabularios y claves referenciales |

La lista es un inventario inicial, no una autorización para copiar indiscriminadamente todas las tablas. Cada tabla debe clasificarse como: dominio vigente, dato histórico/auditoría, estado operativo que continúa, staging temporal o legado descartable. La decisión y recuentos se documentarán en el informe de transformación.

### 6.2 Distribución de atributos que hoy están en Representation

El código actual de resolución SQL obtiene:
- origen y origin_id mediante `COALESCE(representation, work)`;
- licencia mediante `COALESCE(representation, work)`;
- editores desde `representation_persons`;
- características musicales/ejes desde relaciones de Work;
- Resource con un `representation_id`.

En V6 no puede quedar esa precedencia implícita. La transformación debe definir para cada atributo:
- si describe la identidad de Work o el material Resource;
- qué fuente tiene prioridad;
- qué hacer cuando Work y la antigua Representation contienen valores distintos;
- si se conservan ambos valores como procedencia/historial;
- cómo se resuelven editores/personas asociados a una representación antigua.

No se debe copiar ciegamente el valor de Representation a Work. Licencia, origen, edición, editor y otras propiedades pueden variar entre Resources de una misma obra. Cuando describen un material concreto deben quedar en Resource.

### 6.3 Reglas de IDs

- Mantener los IDs actuales de Work si no hay razón técnica para renumerarlos.
- Los IDs de Representation dejan de tener significado en V6; no deben reutilizarse como IDs de Resource sin una regla explícita y auditada.
- Los IDs de Resource/File pueden preservarse cuando sea seguro y facilite referencias externas; la decisión debe ser consistente y reflejarse en el informe.
- La API debe declarar qué tipo de entidad identifica cada ID. Nunca reutilizar un mismo parámetro para resolver indistintamente Work, Resource y File.
- Registrar una tabla de correspondencias de IDs antiguos a nuevos para auditoría, reindexado y diagnóstico, aunque no se mantenga en el esquema de dominio definitivo.

### 6.4 Casos de conflicto que deben producir informe

- Resource sin Work o Work inexistente.
- Resource ligado a Representation inexistente.
- Resource con File inexistente.
- File asociado a más de un Resource.
- File con varias StorageLocations y claves diferentes.
- StorageLocation que apunta a proveedor no identificado o deshabilitado.
- puntero R2 ausente, vacío o no verificable.
- SHA repetido en distintos Files (no deduplicar).
- datos diferentes en Work y Representation para licencia/origen/editor/atributos.
- recurso externo con URL y también File interno.
- archivo de archive_entries que no está enlazado a works_resources.
- archivo de works_resources que no tiene archive_entry.
- claves relativas de mirror que no son claves de R2.
- filas históricas sin correspondencia segura.

Los conflictos no se deben ocultar mediante `COALESCE`, `LIMIT 1`, elección del primer registro o deduplicación automática.

## 7. Cambios internos de osap-storage

### 7.1 Código que actualmente depende del modelo retirado

La inspección confirma dependencias en:
- `domain/entities/representation.py` (define Representation y Resource con representation_id);
- `domain/entities/storage_location.py`;
- `domain/entities/storage_provider.py`;
- `domain/services/availability.py` (availability derivada de StorageLocation);
- `application/services/file_publisher.py` (publicación por provider y StorageLocation);
- `application/services/mirror_resources.py` (crea File + StorageLocation);
- `application/use_cases/delete_file.py` (borra ubicaciones y objetos físicos);
- `application/use_cases/verify_file.py` (verifica cada ubicación);
- repositorios SQL de locations/providers/representations y administración;
- rutas admin de representaciones/recursos, Files, providers, descargas y archivos;
- dependencias e inyección de servicios;
- esquemas Pydantic `ProviderRead`, `LocationRead`, `FileRead.locations`, `ProviderRepresentationDTO`;
- tests, frontend de administración, CLI, tareas y documentación.

El cambio no consiste en renombrar clases. Hay que reconstruir los puertos, casos de uso, repositorios, rutas y pruebas según el nuevo ownership.

### 7.2 Publicación y carga

El actual `FilePublisher` selecciona un StorageProvider, sube el fichero mediante backend y registra StorageLocation. En V6, el backend físico debe seguir existiendo como detalle de infraestructura configurable, pero la operación de dominio debe guardar el puntero directamente en File.

La operación de alta debe ser transaccional desde el punto de vista lógico:
1. crear Resource o localizar el Resource destino;
2. iniciar/ejecutar almacenamiento físico;
3. confirmar que el objeto está guardado;
4. registrar el File con su puntero real;
5. marcar el File como disponible;
6. si la escritura física falla, no dejar un File aparentemente disponible ni una relación rota.

Si el objeto se sube pero falla el commit SQL, debe existir una política de compensación/limpieza idempotente que no borre objetos preexistentes por error. Esta política es para nuevas cargas V6; no se ejecuta durante la migración de objetos ya existentes.

### 7.3 Disponibilidad

Hoy `AvailabilityService` considera disponible un File si existe al menos una StorageLocation en estado stored y el File no está failed. En V6 la disponibilidad debe basarse en el estado del File y la validez de su puntero directo, más la verificación del objeto cuando corresponda.

No se debe interpretar “tiene File” como “objeto comprobado y accesible” sin distinguir estados. Deben definirse estados y transiciones para registrado, pendiente, disponible, fallido y verificación pendiente. El vocabulario final se cerrará al diseñar el DDL/caso de uso.

### 7.4 Borrado y retención

El caso de uso actual `DeleteFile` elimina físicamente todos los objetos enumerados por StorageLocation y después borra File. Este comportamiento es peligroso durante la migración.

- El transformador V6 no debe llamar a `DeleteFile`, `FilePublisher`, `store` ni `delete`.
- El borrado de un Resource no debe borrar automáticamente un objeto físico si existen referencias, retención legal, historial o necesidad de rollback.
- La política V6 de borrado físico debe ser explícita, protegida y separada de la eliminación lógica del registro.
- La migración no borra ni marca como retirados los objetos antiguos.
- La comprobación de referencias debe impedir borrar un File todavía asociado a Resource.

### 7.5 Backend R2 interno

Se puede conservar el adaptador técnico `CloudflareR2Backend` y su configuración privada. La desaparición de StorageProvider como entidad de dominio no exige eliminar el código adaptador. El backend debe recibir bucket, endpoint, credenciales, dominio público y prefijo desde configuración segura.

No deben aparecer `provider_id`, `provider_name`, `StorageLocation` ni rutas físicas internas en DTO públicos de catálogo.

## 8. API de osap-storage consumida por OSAP

### 8.1 Contrato actual observado

El contrato documentado en `docs/provider-api-contract.md` es Provider API v1.3 y describe:

- `GET /api/version`
- `GET /api/lookup?q=...`
- `GET /api/search?q=...`
- `GET /api/resource/{id}`
- `GET /api/download/{resource_id}`

El DTO de Work incluye identidad, metadata, statistics, `resources[]` y en el esquema actual también `representations[]`. El código `api/routes/provider.py` construye actualmente ambos bloques. La documentación afirma que el proveedor no conoce Representations, pero el código y `api/schemas.py` todavía incluyen `ProviderRepresentationDTO`. Esta divergencia es un hallazgo confirmado que debe resolverse.

El endpoint download recibe un parámetro llamado `resource_id`, pero el código actual intenta primero `archive_entries.get_by_file_id(rid)` y luego `representations.get_resource(rid)`. Por tanto, el parámetro puede significar File ID o Resource ID según el resultado. La propia implementación comenta que el índice y enlaces publicados usan en algunos casos file_id. Esta ambigüedad debe desaparecer en V6.

### 8.2 Consumidor OSAP observado

En AI_GAMEPC2:
- `OmrStorageFetcher` consume `/api/search?q=...` y normaliza `works[].resources[].links.download`.
- El fetcher actual toma el primer Resource del array para construir su resultado normalizado.
- Si hay Resource sin archivo descargable, el fetcher conserva la Work pero no crea una descarga.
- El identificador remoto se obtiene primero de `record.id`, con fallback a `file_id` o hash de ruta/URL.
- `providers/omr/endpoints.yaml` declara rutas `/api/v1/search` para lookup/search/resource, mientras que el fetcher de OMR documenta y llama `/api/search`. Hay por tanto dos descripciones de endpoint que deben cotejarse y unificarse.
- El fetcher construye URLs absolutas para enlaces relativos del proveedor.

No se debe suponer que la API interna de Storage es la única consumidora: se deben buscar llamadas directas, conectores, scripts, tareas, pruebas y herramientas administrativas en todos los repositorios que la utilicen.

### 8.3 Decisión recomendada para el contrato V6

Mantener la responsabilidad del servicio: localizar Works, devolver sus datos catalográficos y describir Resources/Files sin exponer almacenamiento interno. Rediseñar el DTO para el modelo Work → Resource → File.

El contrato debe separar explícitamente:
- identificador de Work;
- identificador de Resource;
- identificador de File (solo si alguna operación interna lo necesita);
- metadatos del Resource;
- lista de Files con formato, MIME, tamaño si procede, disponibilidad y enlace de descarga generado por Storage;
- URL externa del Resource cuando corresponda.

La ruta de descarga debe resolver un único tipo de identificador. La opción natural es `/api/download/{resource_id}`, cuyo comportamiento siempre enumera/elige el File según una regla de formato explícita o recibe un file_id en una ruta diferente y nombrada como tal. No debe aceptar un número y adivinar qué tabla contiene ese ID.

La forma exacta del JSON, versión contractual y política de selección de File por formato son decisiones de contrato que deben cerrarse antes de tocar el consumidor. No se declara aquí que la aplicación cliente ya sea compatible con el nuevo DTO.

### 8.4 Matriz de impacto API

| Superficie | Situación actual | Trabajo V6 |
|---|---|---|
| `/api/version` | versión de contrato Provider v1 | decidir versión/identificador contractual V6 |
| `/api/lookup` | índice de Works | conservar semántica; probar velocidad y DTO |
| `/api/search` | Works completas, resources y representations | devolver Work + Resources directos, sin representations |
| `/api/resource/{id}` | Work completa bajo nombre resource | aclarar nombre/semántica; no confundir Work con Resource |
| `/api/download/{id}` | File ID prioritario y fallback Resource ID | resolver un solo tipo de ID |
| `ProviderWorkRead` | incluye representations | eliminar y sustituir por DTO Resource V6 |
| `ProviderResourceDTO` | recurso plano derivado de estructura anterior | definir Resource con Files múltiples |
| autenticación | bearer token opcional en consumidor; scopes configurados | conservar auth/scopes y probar 401/403/expiración |
| URLs | rutas relativas y redirects | conservar enlaces consumibles; no filtrar clave R2 |
| errores | 404/500 según rutas | contrato estable y pruebas de error |

### 8.5 Compatibilidad y despliegue coordinado

No se mantendrá compatibilidad conceptual indefinida con Representation. Aun así, se debe identificar qué versiones de OSAP-API y otros consumidores están desplegadas en el instante del corte.

La estrategia será:
1. implementar el contrato V6 en rama de desarrollo;
2. adaptar OmrStorageFetcher, mapping/endpoints y cualquier otro consumidor;
3. probar ambas partes juntas contra `storage_new`;
4. desplegar servicio y consumidor coordinadamente;
5. no exponer el servicio V6 a un consumidor V5 que espere el DTO antiguo;
6. documentar el número de contrato y comprobarlo al arrancar o en health check.

Si se decide mantener temporalmente una ruta de transición durante el despliegue, será una medida de release controlada, con fecha de retirada, no una segunda arquitectura permanente. La decisión final debe respetar el objetivo de corte único.

## 9. Reconstrucción del índice de OSAP

### 9.1 El índice es derivado

El índice de búsqueda de OSAP vive en la base de datos de osap-api, no es la base de catálogo de osap-storage. Se reconstruye desde proveedores y autoridades canónicas. No debe migrarse como si fuera una copia de Resources/Files.

El índice debe poder regenerarse desde las fuentes V6. La fuente de catálogo para OMR/CPDL es osap-storage; las demás fuentes (IMSLP, Mutopia, MusicBrainz u otras activas) conservan sus propios procesos.

El índice no debe derivarse de R2, claves físicas, hashes ni inventarios de archivos. La existencia de un archivo afecta a disponibilidad/enlace, no a la identidad ni a la indexación de una Work.

### 9.2 Pipeline actual observado

`script/rebuild_index.py`:
- admite proveedores, por defecto `omr,cpdl`;
- con `--full` vacía `index_works`, `index_representations` e `index_work_voicings`;
- ejecuta `script/index_works.py`;
- limpia filas huérfanas de `index_work_voicings`;
- opcionalmente ejecuta IndexNow.

`script/index_works.py` incluye iteradores/procesos para fuentes y, según su documentación y comentarios:
- OMR: lee obras de osap-storage;
- CPDL: corpus materializado en osap-storage;
- IMSLP: Worklist;
- Mutopia: catálogo externo;
- MusicBrainz: dump local.

El proceso de resolución canónica usa `persons` y `persons_aliases` de osap-storage. `script/resolve_index_composers.py` remapea `index_works.person_id` y `composer_name` usando la autoridad de personas y las obras por rol compositor.

`script/sync_index.py` mantiene `sync_state` en osap-api para reanudar sincronizaciones:
- `index.imslp.start`;
- `index.omr.last_work_id`;
- `index.mutopia.start_at`;
- `index.cpdl.last_work_id`.

La sincronización incremental OMR/CPDL usa IDs de Work de osap-storage. Si los IDs se preservan, los cursores pueden seguir siendo válidos tras una revisión; si se renumeran o el conjunto de datos cambia, los cursores deben reiniciarse de forma controlada.

### 9.3 Estructuras derivadas afectadas

El rebuild full vacía expresamente:
- `index_works`;
- `index_representations`;
- `index_work_voicings`.

El nombre `index_representations` es una dependencia explícita de la estructura antigua. V6 elimina Representation del modelo fuente. Antes del corte se debe decidir si:
- esa tabla derivada desaparece;
- se transforma en una tabla de índice de Resources;
- o se sustituye por otra estructura de búsqueda con semántica diferente.

No se debe conservar el nombre `index_representations` fingiendo que todavía existe Representation. Si se necesita indexar materiales, la entidad y campos deben referirse a Resource.

También se debe revisar la tabla `index_work_voicings`: el voicing canónico procede de relaciones de Work con ensembles/voices, y no debe depender de Representation. Debe seguir siendo reconstruible a partir de las relaciones musicales V6.

### 9.4 Cambios necesarios en el indexador OMR/CPDL

Revisar el iterador OMR y CPDL de `script/index_works.py` para retirar:
- referencias a `representations`;
- agrupaciones por `representation_id`;
- campos de salida que dependan de una representación;
- lógica que identifica un material por su ID de File;
- URLs de descarga construidas desde File ID si el contrato V6 define descarga por Resource ID.

La Work debe indexarse aunque no tenga ningún Resource/File descargable. Para cada Work se deben mantener:
- título, compositor/person_id canónico, catálogo y metadatos de búsqueda;
- origen y clave externa cuando se utilicen para incrementalidad;
- ejes musicales derivados de relaciones normalizadas;
- disponibilidad de materiales como atributo separado, sin convertirla en condición para que la Work exista en el índice.

Si el índice mantiene un resumen de recursos, debe derivarse de Resource V6 y sus Files. Debe soportar múltiples Files por Resource sin duplicar una Work en `index_works`.

### 9.5 Pruebas de reconstrucción

En entorno de pruebas:
1. reconstruir completamente el índice V5 desde snapshot congelado y guardar recuentos/muestras de referencia;
2. reconstruir `storage_new` V6;
3. ejecutar rebuild full con los proveedores equivalentes;
4. resolver personas canónicas;
5. comparar conjunto de Works, identidades, títulos, compositores, catálogos, voicings y disponibilidad;
6. clasificar diferencias esperadas por el cambio de modelo;
7. confirmar ausencia de duplicados y huérfanos;
8. ejecutar sincronización incremental dos veces y verificar idempotencia;
9. añadir una Work de prueba y comprobar que entra en la pasada incremental;
10. modificar un Resource/File de prueba y comprobar que el índice actualiza el estado del material sin duplicar Work;
11. probar búsqueda/autocompletado y el pipeline de resolución de obras de OSAP.

La equivalencia no significa que todos los campos antiguos tengan que conservar el mismo nombre. Significa que los resultados funcionales y la información relevante para localizar obras y sus materiales no se pierden.

### 9.6 Estado incremental tras el corte

No copiar ciegamente los valores de `sync_state`. Para OMR y CPDL:
- si Work IDs se conservan y la reconstrucción completa cubre todo el conjunto, establecer cursores al máximo ID validado;
- si los IDs cambian, reiniciar desde cero o reconstruir el estado a partir de la correspondencia de IDs;
- no marcar una fuente como sincronizada antes de finalizar y validar su carga;
- mantener los importadores suspendidos hasta la aceptación.

Los procesos full e incremental no deben ejecutarse simultáneamente sobre el índice durante el corte.

## 10. Importadores, administración y otras integraciones

La revisión de código debe abarcar todos los productores de datos, no solo la API pública.

### 10.1 Importadores

Revisar scripts y tareas que creen o modifiquen:
- Works;
- Resources;
- Files;
- procedencia, licencia y metadatos;
- relaciones de personas/roles;
- conjuntos, voces, idiomas e instrumentación.

En particular, inspeccionar importadores PDMX, CPDL, IMSLP, RISM y cualquier sincronización de autoridad. Toda Work debe tener al menos un Resource. Los importadores que solo reciben una ficha catalográfica deben crear un Resource de referencia únicamente si hay un material/fuente concreta que lo sustente; puede carecer de File. Los Resources importados conservan la fuente como aportante.

No reactivar importadores hasta que:
- sus escrituras apunten al esquema V6;
- no creen Representation;
- no escriban StorageLocation/StorageProvider;
- las claves externas e idempotencia estén validadas;
- el índice pueda sincronizar sus nuevas Works.

### 10.2 Administración

Revisar rutas y frontend de:
- administración de Works;
- administración de Resources;
- administración de Files;
- proveedores y ubicaciones;
- representación/personas asociadas;
- archivos/mirror y descargas.

La interfaz debe reflejar Work → Resource → File. Las operaciones de edición deben diferenciar metadatos catalográficos, metadatos del Resource y metadatos del File. No debe existir una pantalla que permita editar una ubicación física como si fuera una entidad de catálogo.

### 10.3 Resolución y matching

El caso `SqlResolutionSource` actual carga evidencia mediante `works_resources`, LEFT JOIN a `representations`, obtiene origen/licencia mediante COALESCE y editores desde `representation_persons`. Este punto está directamente afectado.

La nueva fuente de resolución debe cargar Resource directamente y obtener:
- Resource ID y tipo;
- procedencia e identificador externo del Resource;
- licencia del Resource;
- metadatos editoriales asociados al Resource;
- Work y sus metadatos;
- compositor y relaciones canónicas;
- ejes musicales de Work o Resource según la semántica aprobada.

No se debe perder evidencia de matching al eliminar Representation. Deben actualizarse los modelos de evidencia, serialización, ranking, explicación y tests de regresión de resolución.

## 11. Pruebas y criterios de aceptación

### 11.1 Datos

- recuento de Works antes/después explicado;
- recuento de Resources antes/después explicado;
- recuento de Files antes/después explicado;
- todos los enlaces Work→Resource válidos;
- todos los enlaces Resource→File válidos;
- cero File compartidos entre Resources;
- cero SHA usados como identidad o restricción única;
- todos los punteros R2 conservados literalmente;
- cero objetos R2 modificados por la migración;
- URL-only Resources conservados;
- historial/auditoría de personas y atribución conservados;
- todas las diferencias y excepciones listadas.

### 11.2 API

- `/api/version` devuelve el contrato V6 esperado;
- lookup/search/detail devuelven DTO V6 sin Representation;
- Work siempre tiene al menos un Resource; comprobar que el índice admite Resources URL-only o sin File;
- Resource sin File aparece como inventario no descargable;
- Resource con varios Files devuelve formatos correctos;
- descarga resuelve un único tipo de ID;
- URL externa se trata según política de seguridad;
- no se filtran hash, clave R2, bucket, endpoint, prefijo ni credenciales;
- auth, scopes, rate limits y errores conservan el comportamiento acordado;
- contrato probado desde OmrStorageFetcher y desde todos los clientes identificados.

### 11.3 R2

- HEAD de muestra y descarga de muestra funcionan;
- URL pública/redirect se construye correctamente;
- el prefijo se aplica exactamente una vez;
- claves con espacios, acentos, caracteres reservados y subdirectorios se prueban;
- los punteros antiguos y nuevos coinciden;
- ningún job de migración llama a métodos de escritura o borrado del backend.

### 11.4 Índice

- rebuild full completa sin consultas a tablas retiradas;
- búsqueda OMR y CPDL devuelve Works esperadas;
- compositores/person_id se resuelven;
- voicings se reconstruyen;
- no se duplica Work por tener varios Resources/Files;
- sincronización incremental idempotente;
- cursores reiniciados o migrados con evidencia;
- pipeline de resolución OSAP funciona con los resultados indexados.

### 11.5 Operación

- snapshot restaurable;
- base V6 separada de producción durante desarrollo;
- guardia de conexión de DB activa;
- todos los productores detenidos durante snapshot final;
- logs y recuentos guardados;
- procedimiento de rollback probado antes de reabrir escrituras;
- despliegue coordinado de osap-storage y OSAP-API;
- importadores reabiertos solo tras aceptación.

## 12. Secuencia de trabajo recomendada

### Fase A — cerrar inventario y contrato

1. Completar el inventario de tablas, relaciones, índices, triggers, vistas y consultas.
2. Completar el inventario de referencias R2 y determinar la clave física efectiva.
3. Definir DDL V6 de Work, Resource y File.
4. Definir la asignación semántica de atributos de Representation a Work/Resource.
5. Definir el contrato API V6 y su versión.
6. Definir la nueva estructura del índice y el mapeo de los cursores incrementales.

**Salida:** especificaciones aprobadas, matriz de mapeo y lista de conflictos.

### Fase B — construir entorno reproducible

1. Snapshot productivo → `storage_old`.
2. Crear `storage_new` desde DDL limpio.
3. Implementar transformador idempotente/repetible.
4. Implementar informe de diferencias y excepciones.
5. Implementar guardia anti-producción.
6. Ejecutar pruebas de datos y R2 en modo de solo lectura para los objetos.

**Salida:** base V6 reconstruible y validada.

### Fase C — adaptar servicios y consumidores

1. Rehacer entidades, puertos, repositorios y casos de uso de osap-storage.
2. Rehacer API Provider y esquemas.
3. Adaptar OmrStorageFetcher y definiciones OMR.
4. Adaptar resolución/matching y metadatos.
5. Adaptar rebuild/sync del índice.
6. Adaptar importadores, administración, tareas y pruebas.

**Salida:** ambos repositorios funcionan juntos contra `storage_new`.

### Fase D — ensayo de corte

1. Ensayar freeze de importadores y jobs.
2. Restaurar snapshot de ensayo.
3. reconstruir storage_new desde cero.
4. ejecutar migración y validaciones completas;
5. desplegar versiones candidatas en entorno controlado;
6. ejecutar rebuild full y pruebas de aceptación;
7. ensayar rollback.

**Salida:** checklist de corte ejecutable, tiempos medidos y responsables identificados.

### Fase E — producción

1. Freeze de todas las escrituras.
2. Snapshot final.
3. Reconstrucción final de V6.
4. Validación completa.
5. Sustitución coordinada de DB y servicios.
6. Rebuild full del índice.
7. Smoke tests y aceptación formal.
8. Reapertura de escrituras e importadores.
9. Mantener DB antigua aislada como rollback temporal y eliminarla solo tras periodo acordado.

## 13. Riesgos prioritarios

| Riesgo | Severidad | Mitigación |
|---|---|---|
| clave R2 interpretada con prefijo doble | crítica | identificar clave efectiva y probar HEAD/GET |
| migración llama por error a delete/upload | crítica | transformador sin acceso de escritura al backend |
| File ID y Resource ID ambiguos | crítica | rutas/DTO tipados y tests de colisión |
| consumidor espera `representations[]` | alta | inventario de clientes y despliegue coordinado |
| índice conserva `index_representations` sin fuente V6 | alta | rediseñar estructura derivada y rebuild full |
| atributos de Representation se pierden o asignan a Work incorrectamente | alta | matriz campo-a-campo y conflictos explícitos |
| cursor incremental deja obras fuera | alta | rebuild full y reinicio/ajuste de sync_state |
| File compartido accidentalmente | alta | detectar cardinalidad y crear File independiente |
| SHA repetido se deduplica | alta | quitar UNIQUE y prohibir dedupe por hash |
| Resource externo se descarta por no tener File | alta | test de Resource URL-only |
| código V6 conecta a DB productiva | crítica | guardia obligatoria de nombre de DB |
| se reanudan importadores antes de aceptar V6 | crítica | freeze documentado y habilitación formal |

## 14. Decisiones aún pendientes — no inventar ni resolver por conveniencia

Los puntos siguientes requieren definición explícita antes de DDL/implementación:

1. DDL exacto de Resource y File: nombres, tipos, nullabilidad, índices y estados.
2. Si el puntero físico se denomina `object_key`, `storage_key` u otro nombre. El concepto es único: referencia opaca y directa al objeto.
3. Si Resource admite varios URLs externos o solo uno.
4. Cómo se selecciona el File preferido para descarga cuando hay varios formatos.
5. Si la descarga se solicita por Resource y negocia formato, o si hay endpoint separado para File.
6. Política de borrado lógico/físico y retención.
7. Tratamiento de datos históricos de Representation sin Resource inequívoco.
8. Tratamiento de `archive_entries` y `archives` en el esquema final: dominio activo, staging o histórico.
9. Qué metadatos y personas editoriales pertenecen al Resource y qué datos se mantienen en Work.
10. Versión exacta del contrato API y si habrá una ruta transitoria limitada durante el corte.
11. Destino de `index_representations`: eliminar, sustituir por índice de Resources o rediseñar el índice completo.
12. Estrategia de IDs de Resource/File y tabla temporal de correspondencias.
13. Política de estados y verificación de Files con punteros R2 existentes.
14. Duración de retención de `osap_storage_old` y condiciones para retirarla.

## 15. Referencias de código revisadas

### AI_osap-storage

- `infrastructure/db/migrations/001_baseline_schema.sql`
- `domain/entities/file.py`
- `domain/entities/representation.py`
- `domain/entities/storage_location.py`
- `domain/entities/storage_provider.py`
- `domain/services/availability.py`
- `application/services/file_publisher.py`
- `application/services/mirror_resources.py`
- `application/use_cases/delete_file.py`
- `application/use_cases/verify_file.py`
- `infrastructure/providers/cloudflare_r2.py`
- `infrastructure/repositories/sql_resolution_source.py`
- `infrastructure/repositories/sql_representation_repository.py`
- `api/routes/provider.py`
- `api/schemas.py`
- `api/dependencies.py`
- `docs/provider-api-contract.md`

### AI_GAMEPC2

- `script/rebuild_index.py`
- `script/index_works.py`
- `script/resolve_index_composers.py`
- `script/sync_index.py`
- `providers/omr/endpoints.yaml`
- `providers/omr/mapping.yaml`
- `src/osap/infrastructure/providers/fetchers/omr_fetcher.py`
- `src/osap/infrastructure/resources/resource_manager.py`
- `docs/osap/v6-work-resource-model.md`
- `docs/osap/v6-storage-locations-removal.md`

---

**Regla final:** V6 debe poder reconstruirse desde una copia congelada de la base antigua, conservar intactos los objetos R2 y demostrar mediante pruebas que API, consumidores e índice funcionan con Work → Resource → File. No se considera terminada la migración por el mero hecho de que el nuevo servicio arranque.

## 15. Área de trabajo personal y aportaciones de usuarios

El alcance V6 incluye también el área privada de trabajo de cada usuario y el flujo de aportación de nuevas piezas o Resources al catálogo. La especificación funcional completa está en [V6 — área de trabajo personal y aportaciones de usuarios](v6-user-workspace-contributions.md). Este bloque debe diseñarse junto con Work → Resource → File: los Files privados usan el mismo modelo de almacenamiento, pero su visibilidad y publicación dependen de la autorización y del flujo editorial de OSAP. No duplicar Works públicas para incorporarlas a un espacio personal.

## 16. Inventario de migración campo a campo y propiedad editorial

El inventario inicial de tablas, campos, referencias R2, reglas de transformación, conflictos y validaciones está en [V6 — inventario de migración de datos y propiedad editorial](v6-data-migration-mapping.md). La regla vigente es que solo el compositor autenticado puede modificar los metadatos catalográficos de Work y solo el creador puede modificar su Resource; cualquier otro usuario aporta un nuevo Resource bajo la misma Work. El inventario está contrastado con migraciones/código versionados, pero aún debe validarse contra el snapshot real de producción.

## Decisión de modelo: autoría, procedencia y derechos

La distribución es vinculante para el contrato, la migración, los importadores y la API V6:

- **Work:** autoría/compositoría de la obra, compartida por todos sus Resources. Una misma Work no admite compositores alternativos según el Resource; si la diferencia refleja obras distintas, debe revisarse la identidad de Work.
- **Resource:** procedencia/aportante (PDMX, IMSLP, CPDL o usuario autenticado) y derechos/licencia aplicables a ese material. Estos datos pueden variar entre Resources de una Work.
- En altas de usuario, el aportante se toma automáticamente de la identidad autenticada; no se pregunta ni se confía en un user_id del cliente.
- El titular de derechos puede ser el compositor o un tercero; no se infiere de autoría ni procedencia.
- Se conserva solo información disponible y necesaria. No se añaden tablas/campos de titularidad, evidencias o historial sin un caso de uso y datos reales. Los valores desconocidos permanecen sin determinar.

Este criterio prevalece sobre cualquier frase anterior que proponga `works_origin`, `works_license` o `works_public_domain` como atributos de Work. En migración, esos datos solo pasan a Resource si su asociación con el material es inequívoca; no se asignan por heurística.


## Corrección vinculante: Work contiene autoría; Resource contiene procedencia y derechos

La autoría/compositoría se define una sola vez en Work y es común a todos sus Resources. Una misma Work no puede tener compositores alternativos según el Resource; si dos materiales tienen autorías incompatibles porque representan obras intelectualmente distintas, debe revisarse la identidad Work. Se admiten coautores reales. La atribución distingue compositor identificado, anónimo declarado, tradicional y desconocido/no resuelto, sin crear personas ficticias.

Cada Resource contiene su procedencia/aportante (fuente externa como PDMX, IMSLP o CPDL, o usuario autenticado) y los derechos/licencia que se conozcan y apliquen a ese material. En altas directas de usuario, el aportante se obtiene de la sesión autenticada; no se pregunta ni se acepta una identidad elegida por el cliente. El titular de derechos puede ser el compositor o un tercero: no se deduce de autoría ni de aportante.

Se aplica un principio de mínima información: no se añaden campos, tablas de titularidad, historiales ni evidencias para escenarios hipotéticos. Se conservan solo datos disponibles, fiables y con uso funcional claro. Lo desconocido queda sin determinar. Los campos históricos de procedencia/licencia en Work solo se trasladan a un Resource si la relación es inequívoca; en otro caso se clasifican como conflicto/no migrable, sin inferencias.

## Regla vinculante de cardinalidad y permisos Work/Resource

Toda Work tiene siempre uno o más Resources. No existe Work sin Resource. Un Resource puede ser URL-only o de referencia y carecer de File; la ausencia de archivo físico no justifica eliminar el Resource ni dejar Work huérfana.

Solo el compositor identificado y autenticado puede modificar los metadatos descriptivos/catalográficos de Work (nombres, títulos, variantes y demás datos de identidad). El permiso de Work no autoriza a modificar Resources creados por terceros. Cada Resource solo puede ser modificado por el usuario que lo creó; en recursos importados, la fuente importadora es el aportante de procedencia. Cualquier otro usuario incorpora su material como un nuevo Resource de la misma Work.

Queda retirada la regla anterior de crear una Work derivada privada al modificar una obra ajena. Los arreglos, ediciones, versiones, partituras y grabaciones aportados por terceros se representan como Resources nuevos. Los créditos específicos de arreglista/editor/intérprete se asocian al Resource concreto cuando sean necesarios y conocidos, sin alterar la autoría de Work.
