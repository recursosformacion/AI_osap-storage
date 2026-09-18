-- Ediciones CPDL: Obra (works) -> Ediciones CPDL -> Ficheros (+ editor como persona, rol 6).
-- Modela el `payload_json` de las páginas CPDL sin duplicar filas en `works`.

SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `cpdl_editions` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `works_id` bigint(20) unsigned NOT NULL,
  `cpdl_editions_cpdlno` int(10) unsigned NOT NULL,
  `cpdl_editions_license` varchar(120) NOT NULL DEFAULT '',
  `cpdl_editions_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_cpdl_editions_cpdlno` (`cpdl_editions_cpdlno`),
  KEY `idx_cpdl_editions_work` (`works_id`),
  CONSTRAINT `fk_cpdl_editions_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `cpdl_edition_files` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `cpdl_editions_id` bigint(20) unsigned NOT NULL,
  `cpdl_edition_files_name` varchar(512) NOT NULL,
  `cpdl_edition_files_type` varchar(16) NOT NULL,
  `cpdl_edition_files_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_cpdl_edition_files_edition` (`cpdl_editions_id`),
  CONSTRAINT `fk_cpdl_edition_files_edition` FOREIGN KEY (`cpdl_editions_id`) REFERENCES `cpdl_editions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `cpdl_edition_persons` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `cpdl_editions_id` bigint(20) unsigned NOT NULL,
  `persons_id` char(36) DEFAULT NULL,
  `roles_id` int(11) NOT NULL DEFAULT 6,
  `cpdl_edition_persons_name` varchar(255) NOT NULL,
  `cpdl_edition_persons_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cpdl_edition_person` (`cpdl_editions_id`, `cpdl_edition_persons_name`, `roles_id`),
  KEY `idx_cpdl_edition_persons_person` (`persons_id`),
  KEY `idx_cpdl_edition_persons_edition` (`cpdl_editions_id`),
  CONSTRAINT `fk_cpdl_edition_persons_edition` FOREIGN KEY (`cpdl_editions_id`) REFERENCES `cpdl_editions` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_cpdl_edition_persons_person` FOREIGN KEY (`persons_id`) REFERENCES `persons` (`persons_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
