-- 010 · Índice para el listado de propuestas de atribución IA.
--
-- El panel siempre lista filtrando por `status` y ordenando por `id DESC`. Sin un índice
-- compuesto, MySQL lee toda la partición del estado y hace filesort en cada página.
-- Idempotente: si ya existe, no hace nada (mismo patrón que 003).

SET @wpa_idx := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'work_person_ai_proposals'
    AND index_name = 'idx_wpa_status_id'
);
SET @wpa_sql := IF(
  @wpa_idx = 0,
  'CREATE INDEX idx_wpa_status_id ON work_person_ai_proposals (status, id)',
  'DO 0'
);
PREPARE wpa_stmt FROM @wpa_sql;
EXECUTE wpa_stmt;
DEALLOCATE PREPARE wpa_stmt;
