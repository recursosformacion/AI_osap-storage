# V6 — área de trabajo personal y aportaciones de usuarios

> **Estado:** especificación funcional y de arquitectura para V6; pendiente de diseño físico detallado, implementación y pruebas.  
> **Fecha:** 2026-10-30.  
> **Modelo de catálogo:** `Work → Resource → File`.  
> **Ámbito:** área privada de usuario, incorporación de obras existentes, creación de material propio y aportación al catálogo común.  
> **Importante:** este documento amplía el alcance V6. No afirma que estas funciones existan ya ni autoriza cambios en producción.

## 1. Objetivo y principios

V6 debe incluir un área de trabajo accesible a usuarios autenticados desde OSAP. No será un segundo catálogo paralelo ni un repositorio de ficheros desconectado: será un espacio personal de organización y preparación de material musical, integrado con el catálogo canónico.

El área personal y el catálogo público tienen responsabilidades diferentes:

- **Catálogo:** identidad compartida de las obras y sus Resources publicados.
- **Área personal:** relaciones, organización y material privado de cada usuario.
- **Aportaciones:** flujo controlado para proponer material nuevo o cambios al catálogo, con revisión y trazabilidad.
- **Storage:** persistencia y entrega de Files; no decide propiedad editorial, permisos de usuario ni aceptación de aportaciones.

Principios obligatorios:

1. Una Work existente se incorpora al espacio de un usuario mediante una relación; no se duplica.
2. La pertenencia a un espacio personal no convierte al usuario en propietario de la Work ni modifica su visibilidad pública.
3. El material privado o pendiente no debe aparecer en búsquedas, páginas públicas, feeds ni índices generales.
4. Una aportación aceptada se integra en las entidades canónicas Work/Resource/File; no se publica una copia paralela.
5. La autoría se define en Work; la procedencia/aportante y los derechos/licencia corresponden a cada Resource. Solo se conserva información disponible y necesaria para el flujo; no se exige ni inventa un titular o una licencia desconocidos.
6. La identidad de usuario se obtiene del contexto autenticado del servidor. Nunca se acepta como autoridad un user_id enviado libremente por el navegador.
7. La autorización se comprueba en servidor para cada operación y cada objeto; ocultar botones en la interfaz no es control de acceso.
8. Los Files privados y pendientes utilizan el mismo modelo File V6 y el mismo adaptador de almacenamiento, pero con control de acceso privado. No se publican URLs permanentes que permitan eludir permisos.
9. No se usa SHA-256 como identidad, deduplicación ni mecanismo de propiedad.
10. Las operaciones sobre el área personal no deben escribir directamente sobre una Work pública sin pasar por el flujo autorizado de edición/revisión.

## 2. Casos de uso incluidos

### 2.1 Incorporar una obra existente al espacio personal

El usuario busca una Work del catálogo y selecciona «Añadir a mi espacio» (o equivalente).

Resultado:
- se crea una relación entre usuario y Work;
- la Work, sus Resources y Files públicos siguen siendo los mismos;
- el usuario puede añadir organización personal, notas o estado de trabajo;
- quitar la Work del espacio personal elimina la relación, no la Work ni sus Resources.

La relación debe ser idempotente: repetir la acción no crea duplicados. La política de visibilidad de notas y etiquetas personales es privada por defecto.

### 2.2 Crear una pieza nueva

Si no existe una Work adecuada, el usuario puede iniciar una pieza nueva desde su área personal.

El borrador debe permitir describir la obra y, si corresponde, asociar uno o más Resources y Files. La creación privada no la hace aparecer automáticamente en el catálogo general.

Antes de crear una Work pública se ejecutará una búsqueda de posibles coincidencias. La decisión de crear una identidad nueva o proponer que se vincule con una Work existente debe ser revisable; no se fusionarán obras automáticamente por similitud de título, compositor o nombre de fichero.

### 2.3 Añadir un Resource a una Work existente

El usuario puede proponer una nueva realización/material para una Work existente: por ejemplo, arreglo, edición, transcripción, partitura, grabación o interpretación.

El Resource propuesto debe quedar diferenciado de los Resources ya publicados hasta que la aportación sea aceptada. Debe guardar la Work objetivo, la descripción del material y, cuando se conozcan, su procedencia/aportante y los derechos/licencia aplicables. La autoría pertenece a Work y no se vuelve a declarar por Resource.

No se debe crear una Work nueva cuando la aportación es simplemente otro Resource de una Work conocida.

### 2.4 Añadir Files a un Resource

Un Resource puede tener varios Files útiles (por ejemplo PDF, MusicXML y MIDI), o ninguno si es una referencia externa URL-only.

Cada File es un artefacto independiente, vinculado a un único Resource. El proceso de carga debe ser transaccional desde el punto de vista lógico: no dejar Files publicados/activos si la transferencia o verificación física falla.

### 2.5 Proponer cambios a datos existentes

La posibilidad de corregir metadatos de Work o Resource se contempla como aportación/revisión, no como edición directa de los datos públicos por cualquier usuario.

El alcance exacto de los campos editables y la posibilidad de que ciertos roles editen directamente sin revisión quedan pendientes de política editorial. La primera versión debe favorecer propuestas explícitas y trazables.

## 3. Separación conceptual y relaciones

El modelo lógico debe representar como mínimo estos conceptos, sin fijar prematuramente nombres definitivos de tablas:

- **UserWorkspace / área personal:** contenedor lógico del espacio de un usuario (puede ser implícito por usuario si no hay necesidad de una entidad independiente).
- **WorkspaceWork / relación personal con Work:** vincula un usuario con una Work existente; incluye fecha de incorporación y estado personal.
- **WorkspaceItem / borrador personal:** representa una pieza o material aún privado, sin identidad pública confirmada.
- **Contribution / aportación:** expediente enviado a revisión; identifica aportante, objetivo, tipo, estado, fechas y decisiones.
- **ContributionWork / Work propuesta:** vincula la aportación con una Work existente o con una nueva Work propuesta.
- **ContributionResource / Resource propuesto:** contiene la descripción del material nuevo o modificado antes de su aceptación.
- **ContributionFile / Files aportados:** relaciona los Files cargados con el expediente y su estado de revisión.
- **ContributionReview / decisiones:** registra revisiones, comentarios, resolución y actor responsable.
- **WorkspaceNote / metadatos personales:** notas, etiquetas o estado de trabajo privados; no se mezclan con los metadatos canónicos.

Estos nombres son etiquetas conceptuales, no DDL aprobado. En el diseño físico se evitarán tablas redundantes si las mismas relaciones pueden representarse con un modelo más sencillo y sin perder trazabilidad.

### 3.1 Relación con Work → Resource → File

- Una Work pública puede estar vinculada a muchos espacios personales sin duplicarse.
- Un borrador de Work no se convierte en Work pública hasta su aceptación/publicación.
- Un Resource propuesto puede apuntar a una Work pública existente o a una Work nueva propuesta.
- Un Resource publicado pertenece directamente a una Work.
- Cada File pertenece a un único Resource.
- Los Files privados/en revisión no se ofrecen mediante el contrato público de descarga.
- La aceptación debe promover o materializar las entidades canónicas conservando IDs/relaciones cuando sea seguro, o registrar una correspondencia explícita si se crea una entidad canónica nueva.

No se debe introducir Representation ni ningún nivel intermedio entre Work y Resource.

## 4. Estados y ciclo de vida

### 4.1 Elementos del espacio personal

Estados personales orientativos:
- activo/en preparación;
- completado;
- archivado;
- eliminado de mi espacio (solo se elimina la relación, salvo borrado explícito del borrador privado).

Son estados del usuario, no estados globales de Work.

### 4.2 Borrador y aportación

Ciclo mínimo propuesto:

`draft → submitted → in_review → accepted | rejected | changes_requested`

- **draft:** solo visible para el aportante y los roles autorizados.
- **submitted:** enviado; el usuario ya no modifica silenciosamente la versión sometida.
- **in_review:** asignado o tomado por un revisor.
- **changes_requested:** requiere correcciones; se conserva la versión revisada y se permite una nueva entrega.
- **accepted:** aceptado para integración/publicación.
- **rejected:** rechazado con motivo; se conserva el expediente según política de retención.

Una aportación aceptada puede necesitar una fase operativa de publicación. Si la publicación falla, el expediente no debe aparecer como completado/publicado; se registra el fallo y puede reintentarse de forma idempotente.

Los estados exactos y transiciones se implementarán como máquina de estados validada en servidor, no como texto libre enviado por el cliente.

### 4.3 Versiones y revisión

Al enviar una aportación se congela una versión de revisión: contenido descriptivo, relaciones propuestas, créditos/licencias declarados y lista de Files. Las modificaciones posteriores crean una nueva versión o una nueva entrega; no reescriben lo que el revisor evaluó.

Cada decisión registra:
- aportación y versión revisada;
- usuario revisor;
- decisión;
- fecha;
- comentario/motivo;
- cambios solicitados, cuando proceda.

La auditoría no debe almacenar innecesariamente copias completas de ficheros o payloads de proveedores; registra los datos mínimos necesarios para explicar la decisión y reproducir el historial.

## 5. Permisos y visibilidad

Matriz mínima:

| Operación | Aportante | Otro usuario | Revisor autorizado | Administrador |
|---|---:|---:|---:|---:|
| Ver su espacio personal | Sí | No | No por defecto | Según política |
| Añadir/quitar Work de su espacio | Sí | No | No | Según soporte |
| Ver/editar sus borradores | Sí | No | Durante revisión si está enviado | Según política |
| Enviar aportación | Sí | No | No | Si actúa como aportante |
| Ver aportación ajena | No | No | Sí, según asignación/rol | Sí |
| Decidir revisión | No | No | Sí | Sí |
| Publicar aceptación | No | No | Según rol/política | Sí o proceso autorizado |
| Modificar Work pública directamente | No | No | Solo si política lo permite | Según permisos |

Reglas:
- Denegar por defecto.
- Comprobar pertenencia/rol en cada endpoint y descarga.
- Separar permisos de lectura del espacio personal, edición del borrador, envío, revisión y publicación.
- Los revisores no obtienen acceso general al espacio personal del usuario: acceden al expediente enviado y a los Files necesarios para revisarlo.
- Los administradores no deben poder eludir el registro de auditoría.
- Las URLs de descarga de Files privados deben ser temporales o servidas por un endpoint autenticado que vuelva a comprobar permisos. La opción concreta depende del mecanismo de entrega de R2, pero nunca se debe exponer la clave física.

Los nombres y scopes concretos de autorización se cerrarán al inspeccionar el sistema de autenticación real de OSAP; este documento no inventa scopes existentes.

## 6. Carga y almacenamiento de Files

El flujo de carga debe coordinar la base de datos y el objeto físico sin dejar referencias rotas:

1. Crear una sesión/operación de carga temporal asociada al usuario y al borrador/aportación.
2. Validar tamaño, MIME/extensión permitidos, cuota y autorización.
3. Recibir el fichero en zona temporal o mediante mecanismo de carga controlada.
4. Guardar el objeto físico usando el adaptador interno de Storage.
5. Verificar que el objeto se ha almacenado y que su tamaño/metadatos concuerdan.
6. Crear/activar el registro File y su relación con Resource/Contribution.
7. Marcar la carga como completada.
8. Ante fallo, registrar estado fallido y limpiar únicamente los temporales que pertenezcan a esa operación; nunca borrar un objeto R2 existente por una compensación ambigua.

El orden exacto puede variar si se utiliza carga directa firmada a R2, pero debe existir una confirmación server-side antes de considerar el File disponible.

Los Files privados no deben entrar en la API pública ni en el índice general antes de la publicación. La promoción de un File privado a público debe conservar el objeto físico cuando sea válido; no requiere volver a subirlo ni cambiar su clave R2.

La eliminación de un borrador no debe borrar automáticamente objetos físicos si existe una referencia o si la propiedad/retención no está demostrada. Debe existir una política de borrado segura, auditable y separada de la simple eliminación de la relación personal.

## 7. Detección de coincidencias y prevención de duplicados

Antes de enviar una nueva Work o Resource:
- buscar posibles Works por título, variantes, compositor, catálogo y otros identificadores;
- mostrar coincidencias al usuario y al revisor;
- permitir proponer «es la misma Work» o «es una Work distinta» con justificación;
- comprobar Resources existentes de la Work objetivo;
- distinguir otro formato del mismo Resource de una nueva realización;
- no fusionar automáticamente por SHA-256, nombre de fichero, tamaño, URL o similitud textual.

El matching produce candidatos, no decisiones canónicas. La resolución final debe quedar registrada y ser reversible solo mediante un procedimiento de corrección auditado.

## 8. Publicación y promoción al catálogo

La aceptación no consiste en copiar indiscriminadamente filas del área personal al catálogo.

Al aceptar:
1. validar de nuevo la Work destino o la creación de una Work nueva;
2. validar los datos requeridos, relaciones de personas/roles y clasificación;
3. validar procedencia y licencia de cada Resource y File;
4. comprobar que los Files necesarios están disponibles;
5. crear o actualizar las entidades canónicas Work/Resource/File en una transacción lógica controlada;
6. conservar el vínculo entre aportación, aportante y entidades resultantes;
7. registrar revisor, decisión, fecha y publicación;
8. emitir/reconstruir las proyecciones de búsqueda e índice;
9. hacer visible el material solo cuando la publicación haya terminado correctamente.

Si se acepta un Resource nuevo para una Work existente, se crea el Resource hijo de esa Work. Si se acepta una Work nueva, se crea Work y sus Resources. Si el expediente es solo una relación personal con una Work existente, no se ejecuta ninguna publicación.

La publicación debe ser idempotente: reintentar una operación no crea Works, Resources ni Files duplicados.

## 9. Integración con búsqueda e índice

- El índice público solo incluye entidades publicadas y visibles.
- Los borradores, aportaciones pendientes y Files privados quedan excluidos.
- La búsqueda del área personal puede combinar catálogo público con las relaciones privadas del usuario, filtrando siempre por el usuario autenticado.
- Al publicar una aportación, se invalida o actualiza la proyección correspondiente; un rebuild completo debe poder reconstruirla desde el catálogo canónico.
- El índice no se convierte en fuente de verdad para propiedad, permisos ni estado editorial.
- Las estadísticas públicas no deben contar borradores ni descargas privadas como si fueran recursos públicos.

## 10. API y superficies de interfaz

Las rutas definitivas se diseñarán al inspeccionar el router y el patrón de autenticación de AI_GAMEPC2. Como capacidades, la API debe cubrir:

- listar y buscar el área personal del usuario autenticado;
- añadir/quitar una Work pública de su espacio;
- consultar y actualizar notas/etiquetas/estado personal;
- crear, consultar, actualizar y eliminar borradores propios;
- iniciar, confirmar y consultar cargas de Files;
- enviar una aportación;
- consultar el estado y las decisiones de sus aportaciones;
- listar expedientes para revisores autorizados;
- registrar decisiones y solicitar cambios;
- publicar una aportación aceptada mediante operación autorizada.

La UI debe diferenciar claramente:
- catálogo público;
- «Mi actividad»/área personal;
- borradores;
- aportaciones enviadas y su estado;
- cola de revisión (solo roles autorizados).

No se debe exponer al usuario una pantalla de administración de Storage ni sus claves/proveedores físicos. El usuario trabaja con obras y materiales musicales.

## 11. Datos personales, cuotas y retención

Antes de abrir cargas a usuarios se deben definir:
- cuota máxima por usuario y por fichero;
- formatos y tamaños permitidos;
- límites de frecuencia y protección frente a abuso;
- tratamiento de malware y contenido no válido;
- retención de borradores abandonados;
- conservación de aportaciones rechazadas y su auditoría;
- exportación y borrado de datos personales cuando corresponda;
- tratamiento de licencias y declaraciones de derechos;
- procedimiento de reclamación/takedown;
- política de copias de seguridad y recuperación.

No se deben inventar límites numéricos hasta conocer la infraestructura, costes y políticas de OSAP. Los límites deben ser configurables y aplicados en servidor.

## 12. Modelo físico: decisiones pendientes antes del DDL

La arquitectura funcional queda definida, pero estos puntos requieren inspección del esquema de autenticación y decisiones de producto antes de fijar tablas y constraints:

1. Si el área personal se materializa con una tabla Workspace por usuario o se deriva directamente de user_id.
2. Si los borradores se almacenan en tablas temporales tipadas o como entidades canónicas con estado privado; se recomienda evitar que borradores contaminen el catálogo público.
3. Cómo representar una Work nueva propuesta sin asignarle prematuramente un ID canónico.
4. Cómo versionar entregas y Files revisados.
5. Roles/scopes reales de revisores y publicadores.
6. Política de notas, etiquetas, colecciones y archivado personal.
7. Política de cuotas, retención y eliminación física.
8. Si las aportaciones pueden incluir modificaciones de Work además de nuevos Resources.
9. Qué información de aportante se muestra públicamente tras aceptación.
10. Si la revisión es manual, por asignación, por cola o con más de un nivel de aprobación.

No se debe resolver ninguno de estos puntos inventando tablas o permisos existentes. El siguiente paso de implementación será una inspección de AI_GAMEPC2/auth y del esquema real para convertir estas decisiones en un DDL concreto.

## 13. Pruebas y criterios de aceptación

### Área personal
- [ ] Una Work pública se añade varias veces sin crear relaciones duplicadas.
- [ ] Dos usuarios pueden añadir la misma Work sin interferir entre sí.
- [ ] Un usuario no puede leer ni modificar el espacio de otro alterando IDs.
- [ ] Quitar una Work del espacio no borra Work, Resource ni File.
- [ ] Notas/etiquetas/estado personal no aparecen en la API pública.

### Borradores y aportaciones
- [ ] Un borrador es privado por defecto.
- [ ] Un usuario no puede enviar una aportación ajena.
- [ ] El envío congela la versión revisada.
- [ ] Las transiciones de estado inválidas son rechazadas.
- [ ] El revisor solo accede a expedientes autorizados.
- [ ] Cada decisión queda auditada.
- [ ] Una aportación rechazada no se publica ni aparece en el índice.

### Work/Resource/File
- [ ] Se puede aportar un Resource a una Work existente.
- [ ] Se puede proponer una Work nueva sin duplicar una Work ya existente.
- [ ] Un Resource admite cero Files y varios Files.
- [ ] Cada File pertenece a un único Resource.
- [ ] Fallar una carga no deja un File disponible sin objeto físico.
- [ ] La descarga privada exige autenticación y autorización.
- [ ] Publicar no requiere volver a subir un objeto R2 válido.
- [ ] La clave física R2 no se expone en respuestas públicas.

### Publicación e índice
- [ ] La aceptación es idempotente.
- [ ] El vínculo aportación → Work/Resource/File publicados queda conservado.
- [ ] Solo los elementos publicados entran en el índice público.
- [ ] El rebuild del índice reproduce el estado publicado.
- [ ] La publicación parcial o fallida no deja datos visibles incoherentes.

## 14. Secuencia de trabajo V6

1. Inspeccionar autenticación, usuarios, roles y scopes reales de AI_GAMEPC2.
2. Cerrar los casos de uso y la política editorial a partir de las capacidades existentes.
3. Diseñar el esquema físico y las constraints de propiedad/visibilidad.
4. Diseñar API y UI de «Mi actividad».
5. Diseñar el flujo de carga privada y su integración con File V6.
6. Implementar borradores, envíos, revisión y publicación.
7. Integrar publicación con el índice y las estadísticas.
8. Añadir pruebas de autorización, aislamiento, idempotencia, carga y publicación.
9. Incluir datos de prueba y migración solo cuando existan registros previos equivalentes; no inventar espacios personales para usuarios sin evidencia.

Este trabajo forma parte del alcance V6 y debe planificarse junto con el corte Work → Resource → File. No se debe posponer como una fase opcional posterior al lanzamiento de V6.

## 2.6 Permisos de edición de Work y Resource (decisión vinculante)

La regla anterior basada en el usuario que subió primero la Work y la copia automática de Work derivadas queda retirada.

1. **Work:** solo su compositor identificado y autenticado puede modificar los metadatos catalográficos: nombres, títulos, variantes y demás datos descriptivos de identidad. Esta facultad no permite modificar Resources creados por otras personas.
2. **Resource:** solo su creador puede modificar ese Resource. El compositor no adquiere permisos sobre Resources de terceros por ser autor de la Work.
3. Cualquier otro usuario que quiera aportar un arreglo, edición, versión, transcripción, partitura, interpretación o grabación crea un **nuevo Resource bajo la misma Work**. No modifica la Work, no sobrescribe Resources existentes y no crea una Work derivada.
4. El creador de un Resource de usuario se obtiene de la sesión autenticada. No se pregunta ni se acepta un user_id enviado por el cliente. Para Resources importados, la procedencia identifica la fuente/sistema que los incorporó.
5. Toda Work debe tener al menos un Resource. Puede ser URL-only o de referencia sin File, pero debe representar un material/fuente real.
6. Añadir una Work a Mi Actividad solo crea una relación personal; no copia Work ni crea Resource.
7. La privacidad/publicación se gestiona por Resource y no cambia la autoría ni los metadatos de Work.
8. La licencia y los derechos aplicables deben respetarse al crear un Resource nuevo. La posibilidad de aportarlo no implica permiso legal para modificar o redistribuir el material.

### Diferencia entre las tres operaciones

| Acción | Resultado | ¿Crea Work? | ¿Puede modificar? |
|---|---|---:|---|
| Añadir al espacio personal | Referencia privada a la Work existente | No | No; solo organización personal |
| Aportar arreglo/edición/versión | Nuevo Resource privado bajo la misma Work | No | Sí, solo ese Resource |
| Modificar metadatos catalográficos | Edición de nombres y demás datos descriptivos por el compositor autenticado | No | Sí, solo metadatos de Work |

No se identifica un propietario editorial de Work a partir del primer aportante. Para registros históricos, la autorización de edición de Work depende de poder vincular al compositor con una cuenta autenticada; la autorización de un Resource depende de poder identificar a su creador. Si esas relaciones no pueden demostrarse, no se concede edición por inferencia.

## Decisión vinculante sobre metadatos de Work y Resource

- La **autoría/compositoría** pertenece a Work y es común a todos sus Resources. Un Resource no puede introducir una autoría alternativa para la misma Work.
- La **procedencia/aportante** y los **derechos/licencia** pertenecen a Resource y pueden variar entre materiales de una misma Work.
- En una aportación directa, el usuario aportante se obtiene de la sesión autenticada; no se pregunta ni se permite que el cliente elija otra identidad.
- El titular de derechos puede ser el compositor o un tercero. No se deduce de la autoría ni de quién sube el material.
- Se guardan solo datos conocidos y necesarios. Los datos desconocidos quedan sin determinar; no se crean entidades ficticias ni estructuras adicionales para escenarios hipotéticos.

### Permisos sin propietario único de Work

No existe una propiedad editorial de Work basada en quién subió el primer Resource. El permiso para modificar los metadatos de Work corresponde al compositor autenticado. El permiso para modificar un Resource corresponde a su creador. La procedencia inicial no concede derechos de edición sobre Work y no se necesita identificar un Resource inicial para aplicar estos permisos.

## Regla de cardinalidad y permisos

Toda Work debe tener al menos un Resource. El Resource puede ser URL-only y no tener File. Work no se crea como ficha vacía a la espera de un Resource.

El compositor autenticado puede modificar los metadatos descriptivos de Work. El creador de un Resource puede modificar exclusivamente ese Resource. Los demás usuarios no duplican Work para aportar material: crean otro Resource bajo la misma Work. No hay un campo editorial_owner de Work derivado del primer aportante.


## Corrección vinculante: Resource original y arreglos; compositor exclusivamente en Work

Esta regla sustituye cualquier frase anterior que permita Resources sin distinguir el original de los arreglos, que admita compositoría en Resource o que deje abierta la selección de un Resource principal:

1. Una Work solo puede existir si tiene al menos un Resource.
2. Al crear una Work, su primer Resource representa el **material original de la obra**. No es un arreglo ni una copia derivada.
3. Los Resources posteriores de esa Work representan **arreglos de la obra original**. No se crea otra Work para un arreglo que conserva la identidad de la misma obra.
4. El compositor o los coautores se relacionan exclusivamente con Work. **No existe relación de compositor en Resource ni se admite el rol de compositor en sus créditos.** Si un material tiene una autoría compositiva diferente, debe tratarse como otra Work, no como Resource de la primera.
5. Los demás créditos personales que describan un Resource (por ejemplo, arreglista, editor, adaptador, intérprete o traductor) se relacionan con ese Resource cuando estén documentados. El arreglista no se convierte por ello en compositor de Work.
6. No se necesita un campo `primary_resource_id`: el Resource original es el primero de la secuencia de creación de la Work y los siguientes son arreglos. El significado original/arreglo debe quedar representado explícitamente en el tipo/clase del Resource, sin deducirlo de que tenga un File, de su fecha de importación o de su proveedor.
7. En Works históricas, solo se clasificará un Resource como original si hay evidencia suficiente. No se elegirá arbitrariamente el primero que aparezca en una consulta ni se inferirá que un Resource es original por ser el más antiguo en la base de datos. Si no puede identificarse el original o no existe material que lo sustente, la Work queda como conflicto de migración y debe resolverse antes del corte; no se inventa un Resource vacío ni se convierte un arreglo en original por conveniencia.
8. La autoría de Work se conserva desde las relaciones de compositoría de Work. Los créditos históricos de Resource se migran excluyendo cualquier rol de compositor; si un crédito revela una composición diferente, se revisa la identidad de Work.

Consecuencias para el DDL y la validación:
- Work debe tener exactamente un Resource original y puede tener cero o más Resources de tipo arreglo.
- Cada Resource pertenece a una única Work y se clasifica como original o arreglo.
- La base de datos/servicio debe impedir más de un Resource original por Work y la aceptación/publicación debe impedir Work sin Resource original. La creación de Work y su Resource original debe ser una única operación lógica/atómica.
- La relación de personas/roles de Resource no admite el rol compositor; la relación de autoría de Work sí.
- La migración debe informar por separado Works sin Resource, Works sin original demostrable, Works con más de un candidato original y Resources cuyo crédito de compositor contradiga la autoría de Work.

---

## Corrección vinculante: aportaciones y Resource de referencia

La creación de una Work y la aportación de Resources no deben imponer la existencia de un Resource original obligatorio.

- Una Work puede existir en el catálogo con cero, uno o varios Resources.
- Un usuario que aporta una partitura, arreglo, edición, transcripción, interpretación o grabación crea un Resource nuevo asociado directamente a la Work correspondiente, respetando permisos y procedencia.
- La aportación no se convierte automáticamente en el Resource de referencia ni se etiqueta como arreglo por ser posterior.
- La Work puede tener opcionalmente un Resource de referencia elegido de entre sus propios Resources. Esa elección destaca el material útil para consultar la obra; no afirma que sea el original histórico.
- Si se conoce y está documentado cuál es la partitura original, puede elegirse ese Resource como referencia y describirse su condición de original. En repertorio clásico, si se desconoce el original, se puede elegir una edición crítica u otro material de referencia, o no elegir ninguno.
- Añadir una Work a «Mi Actividad» sigue siendo una relación personal y no crea un Resource ni modifica la selección de referencia.
- La aportación de un Resource no cambia automáticamente la referencia existente. Cambiarla es una decisión catalográfica explícita y separada de la autoría y de los permisos de edición del Resource.

Se mantiene la separación de permisos: el compositor autenticado puede editar metadatos catalográficos de Work cuando su identidad esté vinculada de forma fiable; cada Resource solo lo modifica su creador. Ser Resource de referencia no concede permisos adicionales ni altera los derechos/licencias.
