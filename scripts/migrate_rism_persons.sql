-- Índice local de autoridades de personas RISM (caché externa, NO toca `persons`).
-- Fuente: RISM dataset (Zenodo 10.5281/zenodo.14846299), MARCXML, CC-BY-3.0.
-- Reconstruible con scripts/import_rism_persons.py.

CREATE TABLE IF NOT EXISTS `rism_persons` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `rism_person_id` varchar(32) NOT NULL,
  `rism_name` varchar(512) NOT NULL,
  `rism_dates` varchar(64) DEFAULT NULL,
  `rism_professions` varchar(512) DEFAULT NULL,
  `rism_is_composer` tinyint(1) NOT NULL DEFAULT 0,
  `rism_gnd` varchar(32) DEFAULT NULL,
  `rism_viaf` varchar(32) DEFAULT NULL,
  `rism_n_variants` int(11) NOT NULL DEFAULT 0,
  `rism_source` varchar(32) NOT NULL DEFAULT 'rism',
  `rism_license` varchar(32) NOT NULL DEFAULT 'CC-BY-3.0',
  `rism_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rism_person` (`rism_person_id`),
  KEY `idx_rism_person_name` (`rism_name`(191)),
  KEY `idx_rism_person_gnd` (`rism_gnd`),
  KEY `idx_rism_person_composer` (`rism_is_composer`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Formas de nombre (principal + variantes) para búsqueda normalizada.
CREATE TABLE IF NOT EXISTS `rism_person_names` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `rism_person_id` varchar(32) NOT NULL,
  `rism_person_names_name` varchar(512) NOT NULL,
  `rism_person_names_normalized` varchar(191) NOT NULL,
  `rism_person_names_matchkey` varchar(191) NOT NULL,
  `rism_person_names_type` varchar(16) NOT NULL DEFAULT 'variant',
  PRIMARY KEY (`id`),
  KEY `idx_rism_names_person` (`rism_person_id`),
  KEY `idx_rism_names_norm` (`rism_person_names_normalized`),
  KEY `idx_rism_names_matchkey` (`rism_person_names_matchkey`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
