-- Historial de cambios de atribución (reversible). No es una entidad de atribución.
CREATE TABLE IF NOT EXISTS `work_attribution_history` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `work_id` bigint(20) unsigned NOT NULL,
  `previous_composer_id` char(36) DEFAULT NULL,
  `new_composer_id` char(36) DEFAULT NULL,
  `source` varchar(32) NOT NULL DEFAULT 'rism',
  `rism_source_id` varchar(32) DEFAULT NULL,
  `rism_person_id` varchar(32) DEFAULT NULL,
  `confidence` varchar(32) DEFAULT NULL,
  `evidence_json` text DEFAULT NULL,
  `operation` varchar(16) NOT NULL DEFAULT 'assign',
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_wah_work` (`work_id`),
  KEY `idx_wah_new` (`new_composer_id`),
  KEY `idx_wah_operation` (`operation`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
