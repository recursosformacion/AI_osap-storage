-- Enlace a la ficha original de la obra en su fuente externa (p. ej. el permalink de
-- IMSLP). Necesario para obras materializadas SOLO como metadatos, sin ficheros
-- redistribuibles: la obra existe en el catálogo y enlaza a la fuente, no la aloja.
ALTER TABLE works
    ADD COLUMN works_source_url VARCHAR(2048) NULL AFTER works_origin_id;
