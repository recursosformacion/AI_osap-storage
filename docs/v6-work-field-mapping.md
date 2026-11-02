# Matriz V6: migración de campos de Work

**Estado:** propuesta de clasificación para revisión de arquitectura.  
**Ámbito:** esquema actual de Storage, contrato OpenAPI V6 y consumidores de OSAP-API.  
**Regla:** esta matriz no autoriza migraciones ni cambios de código. No se han consultado ni modificado bases de datos de producción.

## 1. Criterio de clasificación

V6 separa tres identidades:

- **Work:** la composición musical canónica.
- **Resource:** una materialización, edición, arreglo o interpretación identificada de esa composición.
- **File:** un fichero físico asociado a un único Resource.

La procedencia de un registro externo y los derechos no se deducen de la identidad de Work. La API mantiene además los registros federados externos y los grupos provisionales de búsqueda, que no se convierten automáticamente en Resources de Storage.

En la matriz:

- **Work** significa que el dato describe la composición con independencia de una edición.
- **Resource** significa que el dato depende de una edición, arreglo, transposición, interpretación o material concreto.
- **File** significa que describe el objeto físico o su acceso.
- **Federación/API** significa que conserva identidad o evidencia de una fuente externa sin convertirla automáticamente en material OMR.
- **Revisión** significa que no debe migrarse automáticamente sin inspección semántica.

## 2. Matriz de columnas de `works`

La fuente técnica es `infrastructure/db/migrations/001_baseline_schema.sql`, tabla `works`. Se recogen todas sus columnas funcionales; las marcas de creación/actualización se tratan por separado.

| Columna actual | Destino V6 propuesto | Campo/concepto V6 | Regla de transformación |
|---|---|---|---|
| `id` | Work | `id` | Conservar como identificador legado durante la reconstrucción si no hay colisión; no reutilizarlo como ID de Resource. |
| `works_song_name` | Work | `song_name` | Mantener separado de título si representa el nombre cantable/alternativo. Verificar los pocos registros no nulos y su uso en búsquedas. |
| `works_title` | Work | `title` | Título principal de la composición. |
| `works_subtitle` | Work, sujeto a revisión | `subtitle` | Mantener cuando sea subtítulo propio de la composición; mover a Resource si describe una edición o versión concreta. |
| `works_attr_type` | Work | `attribution_type` | Mantener como estado de atribución de la composición; no crear una persona para anónima, tradicional o popular. |
| `works_attribution_note` | Work | `attribution_note` | Nota de atribución de la composición. |
| `works_opus` | Work | `opus` | Identificador de catálogo/opus asociado a la composición; conservar el texto y no reinterpretarlo como ID interno. |
| `works_catalogue` | Work | `catalogue_references[]` o campo equivalente | Mantener el identificador formateado (p. ej. BWV 846). La estructura final debe permitir más de una referencia si los datos reales lo requieren. |
| `works_musical_key` | Work o Resource | `musical_key` | Work si es tonalidad de la composición; Resource si es tonalidad de una transposición/edición. No asignar sin inspeccionar el contexto. |
| `works_year` | Work, sujeto a precisión | `composition_year` / `date_text` | Solo si representa fecha de composición. Si es fecha de edición, publicación o interpretación, debe quedar en Resource/procedencia. No convertir automáticamente un año ambiguo en fecha exacta. |
| `works_epoch_id` | Work | `epoch_id` o clasificación equivalente | Clasificación temporal de la composición. Conservar la relación con el catálogo de épocas. |
| `works_duration` | Work o Resource | `duration` | Work si es duración estructural/estimada de la composición; Resource si procede de una interpretación o grabación concreta. Revisar valores y consumidores antes de decidir registro a registro. |
| `works_measures` | Work o Resource | `measure_count` | Work si cuenta la estructura de la composición; Resource si el número cambia por edición, repetición, corte o arreglo. |
| `works_pages` | Resource/File | `page_count` | No es atributo de identidad de la composición. Asociar a la edición/material o al documento concreto según su procedencia. |
| `works_parts` | Work o Resource | partes estructurales / partes de edición | Revisar semántica. Partes musicales que forman la composición pueden ser Work; particellas o partes preparadas para una plantilla concreta son Resource. No copiar ciegamente. |
| `works_complexity` | Work o Resource | `complexity` | Solo Work si es una valoración general de la composición; Resource si valora la dificultad de una edición/arreglo concreto. Mantener escala y procedencia si se conocen. |
| `works_description` | Work o Resource | `description` | Separar descripción de la composición de notas sobre edición, arreglo o fichero. No concatenar textos de distinta naturaleza. |
| `works_license` | Resource | `rights/license` | No heredar a Work. Trasladar únicamente cuando exista evidencia de que la licencia se refiere a ese Resource; si la licencia es ambigua, dejar pendiente de revisión. |
| `works_public_domain` | Revisión; normalmente no migrar como booleano de Work | — | No equivale a licencia de un fichero ni demuestra que todos los Resources estén en dominio público. Recalcular solo con política y evidencia explícitas; no inferir derechos del compositor. |
| `works_origin` | Federación/API o procedencia de Resource | `provider` / `source_system` | No es autoría ni propiedad. Si identifica un registro externo, conservar en la relación de fuente externa; si identifica el origen de un Resource incorporado, guardar como procedencia de ese Resource. |
| `works_origin_id` | Federación/API o procedencia de Resource | `source_id` | Conservar junto al identificador del proveedor y tipo de registro. No convertirlo en Work ID canónico ni usarlo como ID de Resource sin comprobar qué entidad identifica. |
| `works_type_file` | File | `format` / `mime_type` | No pertenece a Work. El formato debe describir el fichero real; no confiar solo en el texto legado. |
| `works_obra_iden` | Reconciliación/API; no copiar como FK Work | asociación de identidad pendiente | Es una agrupación/autorreferencia heredada, no prueba suficiente de identidad canónica. Resolver sus grupos antes de asignar Resources a un Work; mantener trazabilidad de la decisión. |
| `works_relative_path` | File, revisión obligatoria | referencia física heredada | No es identidad de Work ni debe convertirse automáticamente en una ruta V6. Investigar si apunta a un fichero local, entrada de archivo o recurso externo. La migración no debe mover ni alterar objetos de R2. |
| `works_music_digest` | Evidencia técnica/revisión; no identidad | — | No usar como ID ni clave de deduplicación. Si se conserva, documentar algoritmo, alcance y procedencia; no asumir que equivale a SHA-256 del File. |
| `works_key` | No migrar como identidad canónica | — | Clave de agrupación heredada. Puede servir como evidencia auxiliar de reconciliación, nunca como identidad definitiva de Work. |
| `works_created_at` | Work | `created_at` | Conservar como fecha del registro si es fiable; no reinterpretar como fecha de composición. |
| `works_updated_at` | Work | `updated_at` | Conservar como fecha técnica del registro. |
| `works_voicing` | Work o Resource | clasificación de plantilla vocal | Separar contexto de composición (Work) de la plantilla de una edición/arreglo (Resource). No mantener un JSON opaco sin contrato; normalizar a vocabulario estructurado cuando corresponda. |
| `works_instrumentation` | Work o Resource | instrumentación | Instrumentación inherente a la composición puede ser Work; plantilla de un arreglo/edición es Resource. Debe contrastarse con las relaciones normalizadas de instrumentos y con los consumidores actuales. |

## 3. Relaciones que no están dentro de la tabla `works`

| Origen actual | Destino V6 | Tratamiento |
|---|---|---|
| `works_person_roles` | Work credits | Migrar créditos de composición/autores al Work. Los roles de Resource no deben entrar aquí. |
| `works_person_import` | Staging/evidencia de atribución | No convertir automáticamente texto importado en créditos resueltos. Mantener pendiente hasta resolver identidad y rol. |
| Roles de compositor en `representation_persons` (modelo anterior) | Work credits, solo tras reconciliación | Un compositor asociado a un material no demuestra por sí solo que sea autor de la composición. Los conflictos se ponen en revisión. |
| Otros roles de `representation_persons` | Resource credits | Migrar como créditos del Resource cuando el vínculo y el rol estén confirmados; excluir compositor. |
| `work_genres`, `work_instruments`, `work_parts`, `work_language`, `work_tags` | Relaciones normalizadas Work/Resource | Revisar cada relación por semántica. No duplicar en JSON si ya existe relación normalizada. |
| `work_statistics` y contadores derivados | Proyección/estadística | Recalcular; no tratarlos como atributos maestros ni como identidad. |

## 4. Contrato OpenAPI V6: campos mínimos que debe cubrir Work

El DTO de Work debe contemplar, como mínimo, estos conceptos:

- Identidad: `id`.
- Denominación: `title`, `song_name`, `subtitle`.
- Atribución: `attribution_type`, `attribution_note`, `composer_credits[]`.
- Referencias: `opus`, `catalogue_references[]`.
- Contexto: `year` (con semántica explícita), `epoch_id`.
- Características musicales confirmadas como propias de la composición: tonalidad, número de compases, partes, complejidad, descripción, instrumentación/plantilla vocal.
- Clasificaciones normalizadas: géneros, idiomas, etiquetas y demás relaciones realmente soportadas por el catálogo.

No deben aparecer en el DTO canónico de Work: ruta física, File ID, formato de fichero, número de páginas de un documento, licencia heredada, booleano de dominio público sin evidencia, proveedor externo como propietario, ni hashes usados como identidad.

El detalle de Work devuelve sus Resources OMR como colección hija. Cada Resource devuelve sus Files como colección hija. Un Work puede no tener Resources OMR en una respuesta federada de búsqueda, aunque la regla del catálogo publicado de Storage exige al menos un Resource.

## 5. Contrato Resource y File relacionado con la migración

**Resource** debe recibir los datos específicos de la materialización:

- tipo/propósito de material (edición, arreglo, transcripción, interpretación u otro vocabulario acordado);
- plantilla vocal e instrumentación cuando describan esa materialización;
- tonalidad, duración, compases, partes o complejidad cuando dependan de esa edición;
- créditos no compositivos;
- procedencia de incorporación y creador autenticado cuando aplique;
- derechos/licencia solo cuando haya evidencia atribuible a ese Resource.

**File** debe recibir los datos del fichero:

- nombre, formato/MIME, tamaño, estado;
- SHA-256 como evidencia de integridad, nunca como identidad o clave única de negocio;
- puntero opaco directo al objeto existente de R2.

La relación es Resource → Files. Cada File pertenece a un único Resource. No se reconstruye una ruta de R2 a partir de hashes ni se copian/mueven/renombran objetos durante la migración de referencias.

## 6. Implicaciones para OSAP-API

Los consumidores de búsqueda y detalle no deben seguir tratando `Representation` como sinónimo universal de Resource.

1. **Búsqueda federada:** devolver por separado Work OMR, materiales externos y grupos provisionales. El registro externo conserva `provider_id` y `source_id`; no se materializa en Storage por aparecer en resultados.
2. **Detalle OMR:** Work → Resources → Files. No aplanar Files como Resources ni inferir File ID desde una URL.
3. **Detalle externo:** usar el adaptador del proveedor con su identidad nativa y discriminantes de variante. Un resultado externo puede ser solo metadatos.
4. **Descarga/visualización:** resolver un identificador opaco de material/acceso a una identidad tipada; no interpretar IDs numéricos como File IDs ni analizar cadenas para extraer Resource ID.
5. **Disponibilidad:** separar existencia del registro, acceso al proveedor, posibilidad de abrir en navegador y descarga efectiva.
6. **Caché/índice:** la clave de Work canónico es su ID reconciliado; los grupos provisionales usan clave explícita provisional. No usar título+compositor ni `works_key` como sustituto de identidad.
7. **Permisos:** autorización sobre Work y Resource se resuelve con identidad de actor autenticada y créditos/creador; nunca confiar en un `user_id` suministrado por el cliente.

## 7. Incompatibilidades heredadas que quedan expresamente retiradas

Los documentos anteriores de conversión y diseño describen decisiones que no deben tomarse como especificación V6:

- Licencia y dominio público almacenados como atributos generales de Work.
- `works_obra_iden` como mecanismo definitivo de agrupación de obras.
- `works_origin` interpretado como email de usuario o proveedor sin distinguir identidad de fuente, actor y procedencia.
- Plantilla vocal e instrumentación siempre almacenadas en Work.
- `works_relative_path` y `works_type_file` como atributos de Work.
- Modelo `Work → Representation → Resource` en Storage.

Estas decisiones se sustituyen por el modelo Work → Resource → File y por la separación entre catálogo OMR y federación externa.

## 8. Revisiones pendientes antes de escribir el migrador

1. Muestrear valores reales de tonalidad, duración, compases, partes, complejidad, descripción, voicing e instrumentación para clasificar composición frente a material.
2. Inspeccionar consumidores de cada campo en API, indexador, SEO, filtros y pantallas; no eliminar un campo solo porque no aparezca en el DTO principal.
3. Auditar `works_obra_iden`, `works_key` y `works_music_digest` como evidencia de reconciliación, sin convertirlos en claves canónicas.
4. Determinar por registro qué significa `works_origin_id` y si identifica Work externo, página, edición o fichero.
5. Revisar licencias y dominio público por Resource con evidencia; los casos ambiguos permanecen sin afirmación de derechos.
6. Confirmar si las clasificaciones vocales/instrumentales son de composición o de edición antes de decidir su entidad.
7. Contrastar el esquema y cardinalidades con el contrato OpenAPI V6 antes de congelar el DDL.

**Criterio de aceptación:** ninguna columna de Work se migra a una entidad solo por compartir nombre o porque la tabla antigua la contuviera. La semántica y el consumidor determinan el destino. Los casos ambiguos se conservan en una cola de revisión, no se resuelven mediante suposiciones.
