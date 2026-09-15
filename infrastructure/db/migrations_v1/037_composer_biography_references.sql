-- 037_composer_biography_references.sql
-- Añade biography_references (JSON) a composer_biographies si la migración 029 no
-- llegó a aplicarla en entornos donde la tabla se creó sin esa columna.
-- Idempotente: no falla si la columna ya existe.

SET @col_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'composer_biographies'
      AND COLUMN_NAME = 'biography_references'
);
SET @ddl = IF(
    @col_exists = 0,
    'ALTER TABLE composer_biographies ADD COLUMN biography_references JSON NULL AFTER biography_key_fact',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
