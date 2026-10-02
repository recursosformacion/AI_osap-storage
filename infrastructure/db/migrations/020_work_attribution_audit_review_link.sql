-- 020 · Fase 6: enlace de `work_attribution_audit` con las decisiones de revisión y reversión exacta.
--
-- Añade a la auditoría:
--   `review_decision_key`   decisión humana que originó la operación (NULL en operaciones legadas)
--   `batch`                 lote de aplicación (p. ej. F6-PROD-0001)
--   `before_json`/`after_json`  estado previo/posterior (atribución y relaciones), para revertir
--   `reverted_at`           marca de reversión (revert = una sola vez por lote)
-- y permite `person_id`/`role_id` NULL para poder auditar cambios de atribución sin relación.
--
-- Idempotente y con guarda de aborto: si al final faltan columnas, la migración no se registra.

SET @has_col := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit'
    AND column_name = 'review_decision_key'
);
SET @sql_col := IF(@has_col = 0,
  'ALTER TABLE `work_attribution_audit` ADD COLUMN `review_decision_key` varchar(255) DEFAULT NULL',
  'DO 0');
PREPARE stmt_col FROM @sql_col; EXECUTE stmt_col; DEALLOCATE PREPARE stmt_col;

SET @has_col := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit' AND column_name = 'batch'
);
SET @sql_col := IF(@has_col = 0,
  'ALTER TABLE `work_attribution_audit` ADD COLUMN `batch` varchar(64) DEFAULT NULL',
  'DO 0');
PREPARE stmt_col FROM @sql_col; EXECUTE stmt_col; DEALLOCATE PREPARE stmt_col;

SET @has_col := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit' AND column_name = 'before_json'
);
SET @sql_col := IF(@has_col = 0,
  'ALTER TABLE `work_attribution_audit` ADD COLUMN `before_json` longtext DEFAULT NULL',
  'DO 0');
PREPARE stmt_col FROM @sql_col; EXECUTE stmt_col; DEALLOCATE PREPARE stmt_col;

SET @has_col := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit' AND column_name = 'after_json'
);
SET @sql_col := IF(@has_col = 0,
  'ALTER TABLE `work_attribution_audit` ADD COLUMN `after_json` longtext DEFAULT NULL',
  'DO 0');
PREPARE stmt_col FROM @sql_col; EXECUTE stmt_col; DEALLOCATE PREPARE stmt_col;

SET @has_col := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit' AND column_name = 'reverted_at'
);
SET @sql_col := IF(@has_col = 0,
  'ALTER TABLE `work_attribution_audit` ADD COLUMN `reverted_at` datetime(6) DEFAULT NULL',
  'DO 0');
PREPARE stmt_col FROM @sql_col; EXECUTE stmt_col; DEALLOCATE PREPARE stmt_col;

-- person_id / role_id deben admitir NULL (filas de cambio de atribución sin relación).
SET @nn := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit'
    AND column_name = 'person_id' AND is_nullable = 'NO'
);
SET @sql_nn := IF(@nn = 1,
  'ALTER TABLE `work_attribution_audit` MODIFY COLUMN `person_id` char(36) DEFAULT NULL',
  'DO 0');
PREPARE stmt_nn FROM @sql_nn; EXECUTE stmt_nn; DEALLOCATE PREPARE stmt_nn;

SET @nn := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit'
    AND column_name = 'role_id' AND is_nullable = 'NO'
);
SET @sql_nn := IF(@nn = 1,
  'ALTER TABLE `work_attribution_audit` MODIFY COLUMN `role_id` int(11) DEFAULT NULL',
  'DO 0');
PREPARE stmt_nn FROM @sql_nn; EXECUTE stmt_nn; DEALLOCATE PREPARE stmt_nn;

SET @has_idx := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit' AND index_name = 'idx_waa_batch'
);
SET @sql_idx := IF(@has_idx = 0,
  'CREATE INDEX `idx_waa_batch` ON `work_attribution_audit` (`batch`)', 'DO 0');
PREPARE stmt_idx FROM @sql_idx; EXECUTE stmt_idx; DEALLOCATE PREPARE stmt_idx;

SET @has_idx := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit'
    AND index_name = 'idx_waa_decision'
);
SET @sql_idx := IF(@has_idx = 0,
  'CREATE INDEX `idx_waa_decision` ON `work_attribution_audit` (`review_decision_key`)', 'DO 0');
PREPARE stmt_idx FROM @sql_idx; EXECUTE stmt_idx; DEALLOCATE PREPARE stmt_idx;

SET @ok := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit'
    AND column_name IN ('review_decision_key', 'batch', 'before_json', 'after_json', 'reverted_at')
);
SET @abort := IF(@ok = 5,
  'DO 0',
  'SELECT * FROM `__migracion_020_abortada__work_attribution_audit_sin_columnas_f6`');
PREPARE stmt_abort FROM @abort; EXECUTE stmt_abort; DEALLOCATE PREPARE stmt_abort;
