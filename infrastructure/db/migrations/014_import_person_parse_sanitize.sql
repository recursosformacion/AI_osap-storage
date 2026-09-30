-- 014 · Saneamiento semántico del staging (fase 3B).
--
-- Añade a `import_person_parse` lo necesario para no confundir "la FK casa" con "la identidad es
-- correcta":
--   `person_name_clean`  nombre saneado por el parser (person_name_raw guarda el texto original)
--   `sanitize_flags`     marcas de la limpieza (json: lead_connector_stripped, truncated_prefix, …)
--   `person_key`         clave lógica de persona (ancla `viaf:…`/`name:<normalizado>`), sin UUID
--
-- `person_name_norm` pasa a ser la normalización del nombre SANEADO (es la clave de resolución y
-- del índice único). La revisión decidirá sobre `person_key`, no sobre el UUID que casó por azar.

SET @has_clean := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'import_person_parse'
    AND column_name = 'person_name_clean'
);
SET @sql_clean := IF(@has_clean = 0,
  'ALTER TABLE `import_person_parse` ADD COLUMN `person_name_clean` varchar(512) DEFAULT NULL AFTER `person_name_raw`',
  'DO 0');
PREPARE stmt_clean FROM @sql_clean; EXECUTE stmt_clean; DEALLOCATE PREPARE stmt_clean;

SET @has_flags := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'import_person_parse'
    AND column_name = 'sanitize_flags'
);
SET @sql_flags := IF(@has_flags = 0,
  'ALTER TABLE `import_person_parse` ADD COLUMN `sanitize_flags` varchar(512) DEFAULT NULL AFTER `person_name_clean`',
  'ALTER TABLE `import_person_parse` MODIFY COLUMN `sanitize_flags` varchar(512) DEFAULT NULL');
PREPARE stmt_flags FROM @sql_flags; EXECUTE stmt_flags; DEALLOCATE PREPARE stmt_flags;

-- `status` debe admitir el vocabulario de 3B: review_target_contaminated (25), resolved_sanitized (18)…
SET @status_len := (
  SELECT character_maximum_length FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'import_person_parse' AND column_name = 'status'
);
SET @sql_status := IF(COALESCE(@status_len, 0) < 32,
  'ALTER TABLE `import_person_parse` MODIFY COLUMN `status` varchar(32) NOT NULL DEFAULT ''pending''',
  'DO 0');
PREPARE stmt_status FROM @sql_status; EXECUTE stmt_status; DEALLOCATE PREPARE stmt_status;

SET @has_key := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'import_person_parse'
    AND column_name = 'person_key'
);
SET @sql_key := IF(@has_key = 0,
  'ALTER TABLE `import_person_parse` ADD COLUMN `person_key` varchar(255) DEFAULT NULL AFTER `role_id`',
  'DO 0');
PREPARE stmt_key FROM @sql_key; EXECUTE stmt_key; DEALLOCATE PREPARE stmt_key;

SET @has_idx := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema = DATABASE() AND table_name = 'import_person_parse'
    AND index_name = 'idx_ipp_person_key'
);
SET @sql_idx := IF(@has_idx = 0,
  'CREATE INDEX `idx_ipp_person_key` ON `import_person_parse` (`person_key`)',
  'DO 0');
PREPARE stmt_idx FROM @sql_idx; EXECUTE stmt_idx; DEALLOCATE PREPARE stmt_idx;

-- Guarda: las tres columnas deben existir y `status` debe admitir los valores nuevos (varchar
-- abierto, sin ENUM, así que basta con comprobar las columnas).
SET @ipp_ok := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'import_person_parse'
    AND column_name IN ('person_name_clean', 'sanitize_flags', 'person_key')
);
SET @ipp_sql := IF(
  @ipp_ok = 3,
  'DO 0',
  'SELECT * FROM `__migracion_014_abortada__import_person_parse_sin_columnas_3b`'
);
PREPARE stmt_ipp FROM @ipp_sql; EXECUTE stmt_ipp; DEALLOCATE PREPARE stmt_ipp;
