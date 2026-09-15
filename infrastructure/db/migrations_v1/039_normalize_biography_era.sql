-- 039_normalize_biography_era.sql
-- Normaliza biography_era: las épocas reales pasan a guardar el id de `epochs`
-- (como texto en la misma columna, que es lo que mostrará el desplegable del Maestro).
-- Solo se tocan valores inequívocos. El ruido (ocupaciones/descripciones wiki) se
-- conserva sin tocar para limpiarlo fila a fila en el mantenimiento: pasarlo al
-- resumen automáticamente puede duplicar contenido si biography_summary ya lo trae.

UPDATE composer_biographies SET biography_era = '2'
 WHERE biography_era IN ('Medieval', 'Edad Media');

UPDATE composer_biographies SET biography_era = '3'
 WHERE biography_era IN ('Renacimiento', 'Renaissance', 'Renacimiento/Reforma', 'Renacimiento/Barroco');

UPDATE composer_biographies SET biography_era = '4'
 WHERE biography_era IN ('Barroco', 'Baroque');

UPDATE composer_biographies SET biography_era = '5'
 WHERE biography_era IN ('Clasicismo', 'Clasicismo/Romanticismo');

UPDATE composer_biographies SET biography_era = '6'
 WHERE biography_era IN ('Romanticismo', 'Romanticismo/Contemporáneo', 'Romanticismo/Siglo XX');

UPDATE composer_biographies SET biography_era = '7'
 WHERE biography_era IN ('Siglo XX', 'Contemporáneo', 'Modernista', 'Impresionismo');
