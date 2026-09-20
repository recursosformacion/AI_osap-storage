-- Índice local de fuentes RISM (caché externa, NO toca `works` ni otras tablas).
-- Fuente: RISM dataset (Zenodo 10.5281/zenodo.14846299), MARCXML, CC-BY-3.0.
-- Reconstruible con scripts/import_rism_sources.py.

CREATE TABLE IF NOT EXISTS `rism_sources` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `rism_source_id` varchar(32) NOT NULL,
  `rism_composer_person_id` varchar(32) DEFAULT NULL,
  `rism_composer_name` varchar(512) DEFAULT NULL,
  `rism_composer_dates` varchar(64) DEFAULT NULL,
  `rism_reliability` varchar(32) DEFAULT NULL,
  `rism_uniform_title` varchar(512) DEFAULT NULL,
  `rism_title` varchar(1024) DEFAULT NULL,
  `rism_language` varchar(64) DEFAULT NULL,
  `rism_shelfmark` varchar(255) DEFAULT NULL,
  `rism_is_anonymous` tinyint(1) NOT NULL DEFAULT 0,
  `rism_has_incipit` tinyint(1) NOT NULL DEFAULT 0,
  `rism_uniform_title_norm` varchar(191) DEFAULT NULL,
  `rism_title_norm` varchar(191) DEFAULT NULL,
  `rism_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rism_source_id` (`rism_source_id`),
  KEY `idx_rism_source_composer` (`rism_composer_person_id`),
  KEY `idx_rism_source_reliability` (`rism_reliability`),
  KEY `idx_rism_source_anonymous` (`rism_is_anonymous`),
  KEY `idx_rism_source_uniform_norm` (`rism_uniform_title_norm`),
  KEY `idx_rism_source_title_norm` (`rism_title_norm`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
