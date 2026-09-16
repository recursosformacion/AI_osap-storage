-- Semillas de catálogos de osap-storage (roles, categorías, roles↔categoría y catálogos
-- musicales). Re-ejecutable (INSERT IGNORE).
--
-- Estas semillas NO venían en ninguna migración del repo: se perdieron al recrear las
-- tablas. Quedan aquí para que la reconstrucción sea reproducible.

INSERT IGNORE INTO `roles` (id, role_name, role_description) VALUES
 (1,'Compositor/a','Creador/a original de la música'),
 (2,'Libretista / Letrista','Autor/a del texto literario'),
 (3,'Arreglista','Adapta la obra a otra plantilla'),
 (4,'Orquestador/a','Distribuye las partes instrumentales'),
 (5,'Transcriptor/a','Traslada la obra a otra notación o medio'),
 (6,'Editor/a Musical','Prepara la edición crítica o académica'),
 (7,'Completador/a','Finaliza obras inconclusas'),
 (8,'Director/a de Orquesta','Lidera la ejecución orquestal'),
 (9,'Director/a de Coro','Prepara y dirige el ensemble vocal'),
 (10,'Intérprete / Solista','Ejecuta una parte solista o principal'),
 (11,'Maestro/a de capilla','Compone, programa y dirige en capilla o corte'),
 (12,'Preparador/a vocal','Ensaya individualmente con cantantes'),
 (13,'Dedicatario/a','Persona a quien se dedica la obra'),
 (14,'Mecenas / Patrocinador/a','Encargó o financió la creación'),
 (15,'Inspirador/a / Musa','Inspiró la temática de la composición');

INSERT IGNORE INTO `category` (id, category_name) VALUES
 (1,'Composición'), (2,'Autoría textual'), (3,'Adaptación y edición'), (4,'Interpretación');

INSERT IGNORE INTO `roles_categoria` (roles_id, category_id) VALUES
 (1,1),(7,1),(11,1),(2,2),(3,3),(4,3),(5,3),(6,3),
 (8,4),(9,4),(10,4),(12,4),(13,1),(14,1),(15,1);

-- `categoryrol(id, categoryrol_name INT)` queda VACÍA: es una tabla heredada con el
-- nombre tipado como entero; la relación real es `roles_categoria`.

INSERT IGNORE INTO `catalog`
 (id, catalog_id, catalog_name, catalog_regex_pattern, catalog_format_template, catalog_description) VALUES
 (1,'BWV','Bach-Werke-Verzeichnis','\\bBWV\\s?(\\d{1,4})\\b','BWV {1}','Catálogo de obras de J. S. Bach'),
 (2,'KV','Köchelverzeichnis','\\bKV\\.?\\s?(\\d{1,4}[a-zA-Z]?)\\b','KV {1}','Catálogo Mozart (Köchel)'),
 (3,'K','Köchel (forma corta)','\\bK\\.?\\s?(\\d{1,4})\\b','K. {1}','Variante abreviada de KV'),
 (4,'Op','Número de opus','\\bOp\\.?\\s?(\\d{1,3})\\b','Op. {1}','Número de obra publicado'),
 (5,'Hob','Hoboken-Verzeichnis','\\bHob\\.?\\s?([IVX]+[:.]\\d{1,3})\\b','Hob. {1}','Catálogo de J. Haydn'),
 (6,'D','Deutsch-Verzeichnis','\\bD\\.?\\s?(\\d{1,4})\\b','D {1}','Catálogo de F. Schubert'),
 (7,'RV','Ryom-Verzeichnis','\\bRV\\.?\\s?(\\d{1,3})\\b','RV {1}','Catálogo de A. Vivaldi'),
 (8,'HWV','Händel-Werke-Verzeichnis','\\bHWV\\.?\\s?(\\d{1,3})\\b','HWV {1}','Catálogo de G. F. Händel'),
 (9,'BuxWV','Buxtehude-Werke-Verzeichnis','\\bBuxWV\\.?\\s?(\\d{1,3})\\b','BuxWV {1}','Catálogo de D. Buxtehude'),
 (10,'Wq','Wotquenne-Verzeichnis','\\bWq\\.?\\s?(\\d{1,3})\\b','Wq. {1}','Catálogo de C. P. E. Bach'),
 (11,'SWV','Schütz-Werke-Verzeichnis','\\bSWV\\.?\\s?(\\d{1,3})\\b','SWV {1}','Catálogo de H. Schütz'),
 (12,'TWV','Telemann-Werke-Verzeichnis','\\bTWV\\s?(\\d{2}[:.]\\d{1,2})\\b','TWV {1}','Catálogo de G. P. Telemann'),
 (13,'WoO','Werke ohne Opuszahl','\\bWoO\\.?\\s?(\\d{1,3})\\b','WoO {1}','Obras sin número de opus');
