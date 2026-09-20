-- 003: índice para resolver personas por alias normalizado.
-- `_resolve_composer_id` (index_works) y los scripts de enlace buscan por
-- `person_aliases_normalized_alias`; sin índice, cada nombre escaneaba la tabla entera
-- (48k filas) y el rebuild del índice OMR pasaba de minutos a horas.
-- Idempotente: si ya existe, no hace nada.
SET @alias_idx := (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'persons_aliases'
      AND index_name = 'idx_persons_aliases_norm'
);
SET @alias_sql := IF(
    @alias_idx = 0,
    'CREATE INDEX idx_persons_aliases_norm ON persons_aliases (person_aliases_normalized_alias)',
    'DO 0'
);
PREPARE alias_stmt FROM @alias_sql;
EXECUTE alias_stmt;
DEALLOCATE PREPARE alias_stmt;
