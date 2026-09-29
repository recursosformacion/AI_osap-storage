-- 009 · Atribución asistida por IA: propuestas y auditoría de asignaciones.
--
-- `work_person_ai_proposals` guarda HIPÓTESIS (nunca escribe en works_person_roles).
-- `work_attribution_audit` audita las asignaciones efectivas y permite revertir: sabe qué
-- relación se creó a partir de qué propuesta (proposal_id).
--
-- ⚠️ NO se reutiliza el nombre `work_attribution_history`: esa tabla ya existe en producción
-- desde `scripts/migrate_work_attribution_history.sql` con OTRO esquema (previous_composer_id/
-- new_composer_id/rism_*, ~136 filas RISM escritas por scripts/apply_rism_attributions.py).
-- Un `CREATE TABLE IF NOT EXISTS` sobre ese nombre sería un no-op silencioso y rompería la
-- aceptación (INSERT con columnas inexistentes) dejando asignaciones sin auditar. La auditoría
-- de la IA vive en una tabla propia y el historial RISM queda intacto.
--
-- Las dos sentencias de comprobación finales abortan la migración (error de tabla inexistente)
-- si el esquema no es el esperado, de modo que el runner no la registre como aplicada.

CREATE TABLE IF NOT EXISTS `work_person_ai_proposals` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `work_id` bigint(20) unsigned NOT NULL,
  `batch_id` varchar(64) DEFAULT NULL,
  `resolution` varchar(16) NOT NULL COMMENT 'identified|anonymous|traditional|unknown',
  `person_match` varchar(16) NOT NULL COMMENT 'matched|ambiguous|unresolved|not_applicable',
  `candidate_person_id` char(36) DEFAULT NULL,
  `candidate_name` varchar(1024) DEFAULT NULL,
  `role_id` int(11) DEFAULT NULL,
  `role_name` varchar(64) DEFAULT NULL,
  `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending|accepted|rejected|uncertain',
  `confidence` decimal(4,3) DEFAULT NULL,
  `model` varchar(64) DEFAULT NULL,
  `prompt_version` varchar(32) DEFAULT NULL,
  `answer_json` longtext DEFAULT NULL,
  `evidence_json` longtext DEFAULT NULL,
  `review_note` varchar(512) DEFAULT NULL,
  `reviewed_by` varchar(128) DEFAULT NULL,
  `reviewed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_wpa_work` (`work_id`),
  KEY `idx_wpa_status` (`status`),
  KEY `idx_wpa_batch` (`batch_id`),
  CONSTRAINT `fk_wpa_work` FOREIGN KEY (`work_id`) REFERENCES `works` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_wpa_person` FOREIGN KEY (`candidate_person_id`) REFERENCES `persons` (`persons_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `work_attribution_audit` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `work_id` bigint(20) unsigned NOT NULL,
  `person_id` char(36) NOT NULL,
  `role_id` int(11) NOT NULL,
  `operation` varchar(16) NOT NULL COMMENT 'assign|remove',
  `source` varchar(32) NOT NULL COMMENT 'gemini|manual|legacy',
  `confidence` decimal(4,3) DEFAULT NULL,
  `proposal_id` bigint(20) unsigned DEFAULT NULL,
  `evidence_json` longtext DEFAULT NULL,
  `created_by` varchar(128) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_waa_work` (`work_id`),
  KEY `idx_waa_person` (`person_id`),
  KEY `idx_waa_proposal` (`proposal_id`),
  CONSTRAINT `fk_waa_work` FOREIGN KEY (`work_id`) REFERENCES `works` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_waa_person` FOREIGN KEY (`person_id`) REFERENCES `persons` (`persons_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_waa_role` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Comprobación A: la auditoría IA debe tener las columnas que escribe el repositorio. Si no
-- (tabla preexistente con otro esquema), abortar en vez de registrar la migración como aplicada.
SET @waa_cols := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_audit'
    AND column_name IN ('work_id', 'person_id', 'role_id', 'proposal_id', 'created_by')
);
SET @waa_sql := IF(
  @waa_cols = 5,
  'DO 0',
  'SELECT * FROM `__migracion_009_abortada__work_attribution_audit_con_esquema_inesperado`'
);
PREPARE waa_stmt FROM @waa_sql;
EXECUTE waa_stmt;
DEALLOCATE PREPARE waa_stmt;

-- Comprobación B: si existe `work_attribution_history`, debe seguir siendo el historial RISM
-- (previous_composer_id). Nada de este fichero la modifica; si alguien la cambió, abortar.
SET @wah_exists := (
  SELECT COUNT(*) FROM information_schema.tables
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_history'
);
SET @wah_rism := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_attribution_history'
    AND column_name = 'previous_composer_id'
);
SET @wah_sql := IF(
  @wah_exists = 0 OR @wah_rism >= 1,
  'DO 0',
  'SELECT * FROM `__migracion_009_abortada__work_attribution_history_no_es_el_historial_rism`'
);
PREPARE wah_stmt FROM @wah_sql;
EXECUTE wah_stmt;
DEALLOCATE PREPARE wah_stmt;
