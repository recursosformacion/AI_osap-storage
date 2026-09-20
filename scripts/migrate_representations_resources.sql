-- Modelo Work -> Representation -> Resource.
-- Fase 1: crear las tablas VACÍAS. No migra ni toca datos.
-- Ver docsNew/diseño-representaciones-recursos.md (§2, §9).
-- `archive_entries` permanece intacto y en paralelo hasta superar las comprobaciones de §9.

SET FOREIGN_KEY_CHECKS = 0;

-- Representación: forma concreta de una obra (edición, versión, arreglo, transcripción, partitura…).
CREATE TABLE IF NOT EXISTS `representations` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `representations_works_id` bigint(20) unsigned NOT NULL,
  `representations_origin` varchar(32) NOT NULL DEFAULT '',
  `representations_origin_id` varchar(191) DEFAULT NULL,
  `representations_origin_cpdlno` int(10) unsigned DEFAULT NULL,
  `representations_type` varchar(32) NOT NULL DEFAULT '',
  `representations_source_name` varchar(512) DEFAULT NULL,
  `representations_license` varchar(120) NOT NULL DEFAULT '',
  `representations_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `representations_updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_representations_origin` (`representations_origin`, `representations_origin_id`),
  KEY `idx_representations_work` (`representations_works_id`),
  KEY `idx_representations_cpdlno` (`representations_origin_cpdlno`),
  CONSTRAINT `fk_representations_work` FOREIGN KEY (`representations_works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Recurso: fichero que materializa una representación (MXL, PDF, MIDI…).
-- `file_id` (interno) y `url` (externo) son excluyentes en la práctica, pero ambos opcionales:
-- permite inventariar sin descargar.
CREATE TABLE IF NOT EXISTS `works_resources` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `works_resources_representation_id` bigint(20) unsigned NOT NULL,
  `works_resources_type` varchar(16) NOT NULL DEFAULT '',
  `works_resources_name` varchar(512) NOT NULL DEFAULT '',
  `works_resources_relative_path` varchar(1024) DEFAULT NULL,
  `works_resources_status` varchar(30) NOT NULL DEFAULT '',
  `works_resources_file_id` bigint(20) unsigned DEFAULT NULL,
  `works_resources_url` varchar(1024) DEFAULT NULL,
  `works_resources_archive_id` bigint(20) unsigned DEFAULT NULL,
  `works_resources_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `works_resources_updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_works_resources_representation` (`works_resources_representation_id`),
  KEY `idx_works_resources_file` (`works_resources_file_id`),
  KEY `idx_works_resources_archive` (`works_resources_archive_id`),
  CONSTRAINT `fk_works_resources_representation` FOREIGN KEY (`works_resources_representation_id`) REFERENCES `representations` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_works_resources_file` FOREIGN KEY (`works_resources_file_id`) REFERENCES `files` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_works_resources_archive` FOREIGN KEY (`works_resources_archive_id`) REFERENCES `archives` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Personas de una representación (editor CPDL, rol 6…).
CREATE TABLE IF NOT EXISTS `representation_persons` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `representation_persons_representation_id` bigint(20) unsigned NOT NULL,
  `representation_persons_person_id` char(36) DEFAULT NULL,
  `representation_persons_role_id` int(11) NOT NULL DEFAULT 6,
  `representation_persons_name` varchar(255) NOT NULL,
  `representation_persons_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_representation_person` (`representation_persons_representation_id`, `representation_persons_name`, `representation_persons_role_id`),
  KEY `idx_representation_persons_representation` (`representation_persons_representation_id`),
  KEY `idx_representation_persons_person` (`representation_persons_person_id`),
  CONSTRAINT `fk_representation_persons_representation` FOREIGN KEY (`representation_persons_representation_id`) REFERENCES `representations` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_representation_persons_person` FOREIGN KEY (`representation_persons_person_id`) REFERENCES `persons` (`persons_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
