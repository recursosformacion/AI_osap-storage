-- 002: índice FULLTEXT para la búsqueda RISM local (`rism_sources`, ~1,5M filas).
-- Sin él, `search` usaba LIKE '%q%' → full scan (~17 s); con MATCH … AGAINST baja a ms.
-- Idempotente: si el índice ya existe, no hace nada (MySQL no admite IF NOT EXISTS).
SET @ft_exists := (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'rism_sources'
      AND index_name = 'ft_rism_search'
);
SET @ft_sql := IF(
    @ft_exists = 0,
    'ALTER TABLE rism_sources ADD FULLTEXT INDEX ft_rism_search (rism_uniform_title, rism_title, rism_composer_name)',
    'DO 0'
);
PREPARE ft_stmt FROM @ft_sql;
EXECUTE ft_stmt;
DEALLOCATE PREPARE ft_stmt;
