-- 033_works_composer_backfill.sql
-- Rellena works.composer_id (NULL) desde composers por coincidencia exacta de
-- works.composer con composers.name, y en segunda pasada con composer_aliases.alias
-- (la tabla de alias es la fuente de identidad de osap-storage). Idempotente.

UPDATE works w
JOIN composers c ON c.name = w.composer
SET w.composer_id = c.id
WHERE w.composer_id IS NULL
  AND w.composer IS NOT NULL AND TRIM(w.composer) <> '';

UPDATE works w
JOIN composer_aliases ca ON ca.alias = w.composer
SET w.composer_id = ca.composer_id
WHERE w.composer_id IS NULL
  AND w.composer IS NOT NULL AND TRIM(w.composer) <> '';
