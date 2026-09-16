
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `archive_entries` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `archive_id` bigint(20) unsigned NOT NULL,
  `logical_id` varchar(255) DEFAULT NULL,
  `composer` text DEFAULT NULL,
  `title` text DEFAULT NULL,
  `work_id` bigint(20) unsigned DEFAULT NULL,
  `relative_path` varchar(1024) NOT NULL,
  `file_id` bigint(20) unsigned DEFAULT NULL,
  `size` bigint(20) DEFAULT NULL,
  `offset_bytes` bigint(20) DEFAULT NULL,
  `status` varchar(30) NOT NULL DEFAULT 'missing',
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_archive_entries` (`archive_id`,`relative_path`) USING HASH,
  KEY `idx_archive_entries_archive` (`archive_id`),
  KEY `idx_archive_entries_logical` (`logical_id`),
  KEY `idx_archive_entries_file` (`file_id`),
  KEY `idx_archive_entries_status` (`status`),
  CONSTRAINT `fk_archive_entries_archive` FOREIGN KEY (`archive_id`) REFERENCES `archives` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_archive_entries_file` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=254082 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `archives` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `provider_id` bigint(20) unsigned DEFAULT NULL,
  `name` varchar(512) NOT NULL,
  `url` varchar(2048) DEFAULT NULL,
  `format` varchar(30) NOT NULL DEFAULT 'tar',
  `local_path` varchar(1024) DEFAULT NULL,
  `status` varchar(30) NOT NULL DEFAULT 'imported',
  `size` bigint(20) DEFAULT NULL,
  `sha256` char(64) DEFAULT NULL,
  `downloaded_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_archives_name` (`name`),
  KEY `idx_archives_provider` (`provider_id`),
  CONSTRAINT `fk_archives_provider` FOREIGN KEY (`provider_id`) REFERENCES `storage_providers` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `authority_sync_state` (
  `source` varchar(32) NOT NULL,
  `last_packet` bigint(20) unsigned NOT NULL DEFAULT 0,
  `last_success_at` datetime(6) DEFAULT NULL,
  `last_error` varchar(512) DEFAULT NULL,
  `metadata_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`metadata_json`)),
  PRIMARY KEY (`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `catalog` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `catalog_id` varchar(30) NOT NULL COMMENT '''BWV'', ''K'', ''Op'', ''WoO'', ''HWV''',
  `catalog_name` varchar(150) NOT NULL COMMENT '''Opus'', ''Bach-Werke-Verzeichnis'', etc.',
  `catalog_regex_pattern` varchar(255) NOT NULL COMMENT 'Patrón Regex para detectar en el título',
  `catalog_format_template` varchar(100) NOT NULL COMMENT 'Formato estandarizado de salida',
  `catalog_description` text DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Solo define las reglas de reconocimiento y formato del catál';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `category` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `category_name` varchar(150) NOT NULL COMMENT '''composer'', ''creation'', ''performance'', ''social''''dedicatee''',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `categoryrol` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `categoryrol_name` int(11) NOT NULL COMMENT '''creation'', ''performance'', ''social''',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `download_jobs` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `file_id` bigint(20) unsigned NOT NULL,
  `provider_id` bigint(20) unsigned DEFAULT NULL,
  `source_url` varchar(2048) NOT NULL,
  `status` varchar(30) NOT NULL DEFAULT 'pending',
  `error_message` text DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_download_jobs_file` (`file_id`),
  KEY `idx_download_jobs_status` (`status`),
  KEY `fk_download_jobs_provider` (`provider_id`),
  CONSTRAINT `fk_download_jobs_file` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_download_jobs_provider` FOREIGN KEY (`provider_id`) REFERENCES `storage_providers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ensemble_voices` (
  `ensembles_id` int(10) unsigned NOT NULL,
  `voices_id` int(10) unsigned NOT NULL,
  `ensemble_voices_quantity` int(11) NOT NULL DEFAULT 1,
  `ensemble_voices_order` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`ensembles_id`,`voices_id`),
  KEY `idx_ensemble_voices_voice` (`voices_id`),
  CONSTRAINT `fk_ensemble_voices_ensemble` FOREIGN KEY (`ensembles_id`) REFERENCES `ensembles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ensemble_voices_voice` FOREIGN KEY (`voices_id`) REFERENCES `voices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ensembles` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `ensembles_name` varchar(120) NOT NULL,
  `ensembles_code` varchar(40) NOT NULL,
  `ensembles_description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ensembles_code` (`ensembles_code`)
) ENGINE=InnoDB AUTO_INCREMENT=393 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `epochs` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `title` varchar(140) NOT NULL,
  `year_start` int(11) DEFAULT NULL COMMENT 'año inicio (NULL = sin límite inferior)',
  `year_end` int(11) DEFAULT NULL COMMENT 'año fin (NULL = hasta la actualidad)',
  `description` text NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_epoch_title` (`title`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `files` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `sha256` char(64) DEFAULT NULL,
  `name` varchar(512) NOT NULL,
  `mime_type` varchar(255) DEFAULT NULL,
  `size_bytes` bigint(20) DEFAULT NULL,
  `status` varchar(30) NOT NULL DEFAULT 'registered',
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_files_sha256` (`sha256`),
  KEY `idx_files_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=254659 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `genre_mappings` (
  `code` varchar(60) NOT NULL,
  `genre_id` int(10) unsigned NOT NULL,
  PRIMARY KEY (`code`),
  KEY `fk_genre_mapping_genre` (`genre_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `genres` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(140) NOT NULL,
  `description` text NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_genre_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `import_sources` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `provider` varchar(100) NOT NULL,
  `version` varchar(100) DEFAULT NULL,
  `csv_path` varchar(1024) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `imported_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_import_sources_provider` (`provider`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `instrument_categories` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(40) NOT NULL,
  `name` varchar(120) NOT NULL,
  `mb_type` varchar(40) NOT NULL DEFAULT '',
  `parent_id` int(10) unsigned DEFAULT NULL,
  `sort` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_inst_cat_code` (`code`),
  KEY `fk_inst_cat_parent` (`parent_id`)
) ENGINE=InnoDB AUTO_INCREMENT=109 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `instruments` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(60) NOT NULL,
  `category_id` int(10) unsigned NOT NULL,
  `name_en` varchar(120) NOT NULL,
  `name_es` varchar(120) NOT NULL,
  `aliases` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`aliases`)),
  `imslp_codes` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`imslp_codes`)),
  `clef` varchar(16) DEFAULT NULL,
  `voicing_parts` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`voicing_parts`)),
  `sort` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_instrument_code` (`code`),
  KEY `fk_instrument_cat` (`category_id`)
) ENGINE=InnoDB AUTO_INCREMENT=182 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `languages` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `languages_code` varchar(16) NOT NULL,
  `languages_name` varchar(120) DEFAULT NULL,
  `languages_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `languages_updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_languages_code` (`languages_code`)
) ENGINE=InnoDB AUTO_INCREMENT=246 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `persons` (
  `persons_id` char(36) NOT NULL,
  `persons_name` varchar(1024) NOT NULL,
  `persons_visible` tinyint(1) NOT NULL DEFAULT 0,
  `persons_givenname` varchar(512) DEFAULT NULL,
  `persons_familyname` varchar(512) DEFAULT NULL,
  `persons_sortname` varchar(1024) DEFAULT NULL,
  `persons_birth_year` varchar(16) DEFAULT NULL,
  `persons_death_year` varchar(16) DEFAULT NULL,
  `persons_status` varchar(16) NOT NULL DEFAULT 'active',
  `persons_review_status` varchar(16) NOT NULL DEFAULT 'not_reviewed',
  `persons_review_reason` varchar(64) DEFAULT NULL,
  `persons_reviewed_at` datetime(6) DEFAULT NULL,
  `persons_merged_into` char(36) DEFAULT NULL,
  `persons_merged_at` datetime(6) DEFAULT NULL,
  `persons_source_system` varchar(32) NOT NULL DEFAULT 'maestro',
  `persons_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `persons_updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  `persons_biography_summary` text DEFAULT NULL,
  `persons_biography_era` varchar(64) DEFAULT NULL,
  `persons_biography_nationality` varchar(64) DEFAULT NULL,
  `persons_biography_key_works` longtext DEFAULT NULL,
  `persons_biography_key_fact` varchar(255) DEFAULT NULL,
  `persons_biography_references` longtext DEFAULT NULL,
  `persons_biography_updated_at` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`persons_id`),
  KEY `idx_persons_name` (`persons_name`(255)),
  KEY `idx_persons_visible` (`persons_visible`),
  KEY `idx_persons_status` (`persons_status`),
  KEY `idx_persons_review_status` (`persons_review_status`),
  KEY `idx_persons_merged_into` (`persons_merged_into`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `persons_aliases` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `person_id` char(36) NOT NULL,
  `person_aliases_alias` varchar(1024) NOT NULL,
  `person_aliases_normalized_alias` varchar(1024) NOT NULL,
  `person_aliases_name_type` varchar(32) NOT NULL DEFAULT 'alias',
  `person_aliases_language_id` int(11) DEFAULT NULL,
  `person_aliases_source` varchar(32) NOT NULL DEFAULT 'musicbrainz',
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_composer_alias` (`person_id`,`person_aliases_normalized_alias`(255)),
  KEY `idx_composer_aliases_composer` (`person_id`)
) ENGINE=InnoDB AUTO_INCREMENT=39778 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `persons_authority` (
  `authority_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `persons_id` char(36) DEFAULT NULL,
  `persons_authority_wikidata_id` varchar(16) DEFAULT NULL,
  `persons_authority_viaf_id` varchar(32) DEFAULT NULL,
  `persons_authority_imslp_id` varchar(255) DEFAULT NULL,
  `persons_authority_canonical_name` varchar(255) NOT NULL,
  `persons_authority_birth_date` varchar(20) DEFAULT NULL,
  `persons_authority_death_date` varchar(20) DEFAULT NULL,
  `persons_authority_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`authority_id`),
  KEY `idx_persons_authority_person` (`persons_id`),
  KEY `idx_persons_authority_wikidata` (`persons_authority_wikidata_id`),
  KEY `idx_persons_authority_viaf` (`persons_authority_viaf_id`),
  CONSTRAINT `fk_persons_authority_person` FOREIGN KEY (`persons_id`) REFERENCES `persons` (`persons_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=34479 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `persons_authority_name` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `authority_id` bigint(20) unsigned NOT NULL,
  `persons_authority_name_name` varchar(255) NOT NULL,
  `persons_authority_name_normalized_name` varchar(128) NOT NULL,
  `persons_authority_name_source` varchar(32) NOT NULL DEFAULT 'wikidata',
  `persons_authority_name_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_persons_authority_name_authority` (`authority_id`),
  KEY `idx_persons_authority_name_normalized` (`persons_authority_name_normalized_name`),
  CONSTRAINT `fk_persons_authority_name_authority` FOREIGN KEY (`authority_id`) REFERENCES `persons_authority` (`authority_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=30149 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `persons_evidence` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `persons_id` char(36) NOT NULL,
  `persons_evidence_rule` varchar(64) NOT NULL,
  `persons_evidence_decision` varchar(16) NOT NULL,
  `persons_evidence_reason` varchar(64) NOT NULL,
  `persons_evidence_anchor_type` varchar(24) NOT NULL DEFAULT 'none',
  `persons_evidence_anchor_value` varchar(255) NOT NULL DEFAULT 'none',
  `persons_evidence_channels` longtext DEFAULT NULL,
  `persons_evidence_identifiers_used` longtext DEFAULT NULL,
  `persons_evidence_matcher_version` varchar(32) NOT NULL,
  `persons_evidence_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_persons_evidence_person` (`persons_id`),
  CONSTRAINT `fk_persons_evidence_person` FOREIGN KEY (`persons_id`) REFERENCES `persons` (`persons_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2937 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `persons_identifiers` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `persons_id` char(36) NOT NULL,
  `persons_identifiers_type` varchar(24) NOT NULL,
  `persons_identifiers_value` varchar(255) NOT NULL,
  `persons_identifiers_source` varchar(32) NOT NULL DEFAULT '',
  `persons_identifiers_is_identity_anchor` tinyint(1) NOT NULL DEFAULT 0,
  `persons_identifiers_strength` varchar(16) DEFAULT NULL,
  `persons_identifiers_channels` longtext DEFAULT NULL,
  `persons_identifiers_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_persons_identifiers_person` (`persons_id`),
  KEY `idx_persons_identifiers_type` (`persons_identifiers_type`),
  CONSTRAINT `fk_persons_identifiers_person` FOREIGN KEY (`persons_id`) REFERENCES `persons` (`persons_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=11961 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `persons_merge_history` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `merge_operation_id` char(36) DEFAULT NULL,
  `source_person_id` char(36) NOT NULL,
  `target_person_id` char(36) NOT NULL,
  `merged_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `merged_by` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_persons_merge_source` (`source_person_id`),
  KEY `idx_persons_merge_target` (`target_person_id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `roles` (
  `id` int(11) NOT NULL,
  `role_name` varchar(30) NOT NULL COMMENT '''composer'', ''arranger'', ''librettist'', ''dedicatee''',
  `role_description` varchar(100) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `roles_categoria` (
  `roles_id` int(11) NOT NULL,
  `category_id` int(11) NOT NULL,
  PRIMARY KEY (`roles_id`,`category_id`),
  KEY `fk_roles_categoria_category` (`category_id`),
  CONSTRAINT `fk_roles_categoria_category` FOREIGN KEY (`category_id`) REFERENCES `category` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_roles_categoria_role` FOREIGN KEY (`roles_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `schema_migrations` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `applied_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_schema_migrations_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `statistics` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `archives` bigint(20) NOT NULL DEFAULT 0,
  `entries` bigint(20) NOT NULL DEFAULT 0,
  `files` bigint(20) NOT NULL DEFAULT 0,
  `downloaded_tar` bigint(20) NOT NULL DEFAULT 0,
  `materialized` bigint(20) NOT NULL DEFAULT 0,
  `pending` bigint(20) NOT NULL DEFAULT 0,
  `bytes` bigint(20) NOT NULL DEFAULT 0,
  `computed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `statistics_runs` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `started_at` datetime(6) NOT NULL,
  `finished_at` datetime(6) DEFAULT NULL,
  `works_updated` int(11) NOT NULL DEFAULT 0,
  `composers_updated` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=73 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `storage_locations` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `file_id` bigint(20) unsigned NOT NULL,
  `provider_id` bigint(20) unsigned NOT NULL,
  `object_key` varchar(1024) NOT NULL,
  `status` varchar(30) NOT NULL DEFAULT 'stored',
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_storage_locations_file_provider` (`file_id`,`provider_id`),
  KEY `idx_storage_locations_provider` (`provider_id`),
  CONSTRAINT `fk_storage_locations_file` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_storage_locations_provider` FOREIGN KEY (`provider_id`) REFERENCES `storage_providers` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=254658 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `storage_providers` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `provider_type` varchar(50) NOT NULL,
  `config` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`config`)),
  `enabled` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_storage_providers_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `tag_work` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `tag_texto` varchar(512) NOT NULL,
  `tag_descripcion` text DEFAULT NULL,
  `tag_work_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tag_work_texto` (`tag_texto`)
) ENGINE=InnoDB AUTO_INCREMENT=32768 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `voices` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `voices_name` varchar(80) NOT NULL,
  `voices_sort` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_voices_name` (`voices_name`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `votes` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `user_id` varchar(255) NOT NULL,
  `work_id` bigint(20) unsigned NOT NULL,
  `vote` tinyint(4) NOT NULL,
  `voted_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `vote_day` date NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_votes_user_work_day` (`user_id`,`work_id`,`vote_day`),
  KEY `idx_votes_work` (`work_id`),
  KEY `idx_votes_day` (`vote_day`),
  CONSTRAINT `chk_votes_range` CHECK (`vote` between 1 and 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_ensembles` (
  `works_id` bigint(20) unsigned NOT NULL,
  `ensembles_id` int(10) unsigned NOT NULL,
  `work_ensembles_quantity` int(11) NOT NULL DEFAULT 1,
  PRIMARY KEY (`works_id`,`ensembles_id`),
  KEY `idx_work_ensembles_ensemble` (`ensembles_id`),
  CONSTRAINT `fk_work_ensembles_ensemble` FOREIGN KEY (`ensembles_id`) REFERENCES `ensembles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_work_ensembles_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_genres` (
  `works_id` bigint(20) unsigned NOT NULL,
  `genres_id` int(10) unsigned NOT NULL,
  `work_genres_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`works_id`,`genres_id`),
  KEY `idx_work_genres_genre` (`genres_id`),
  CONSTRAINT `fk_work_genres_genre` FOREIGN KEY (`genres_id`) REFERENCES `genres` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_work_genres_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_instruments` (
  `works_id` bigint(20) unsigned NOT NULL,
  `instruments_id` int(10) unsigned NOT NULL,
  `work_instruments_quantity` int(11) NOT NULL DEFAULT 1,
  `work_instruments_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`works_id`,`instruments_id`),
  KEY `idx_work_instruments_instrument` (`instruments_id`),
  CONSTRAINT `fk_work_instruments_instrument` FOREIGN KEY (`instruments_id`) REFERENCES `instruments` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_work_instruments_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_language` (
  `works_id` bigint(20) unsigned NOT NULL,
  `languages_id` int(10) unsigned NOT NULL,
  `work_language_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`works_id`,`languages_id`),
  KEY `idx_work_language_language` (`languages_id`),
  CONSTRAINT `fk_work_language_language` FOREIGN KEY (`languages_id`) REFERENCES `languages` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_work_language_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_parts` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `works_id` bigint(20) unsigned NOT NULL,
  `work_parts_name` varchar(512) NOT NULL,
  `work_parts_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_work_parts_work` (`works_id`),
  CONSTRAINT `fk_work_parts_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=458746 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_statistics` (
  `works_id` bigint(20) unsigned NOT NULL,
  `wksta_vote_count` int(11) NOT NULL DEFAULT 0,
  `wksta_work_count` int(11) NOT NULL DEFAULT 1,
  `wksta_confidence` decimal(5,4) DEFAULT NULL,
  `wksta_rating` decimal(10,3) DEFAULT NULL,
  `wksta_adjusted_rating` decimal(10,3) DEFAULT NULL,
  `wksta_calculated_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`works_id`),
  CONSTRAINT `fk_work_statistics_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_tag` (
  `works_id` bigint(20) unsigned NOT NULL,
  `tag_id` int(10) unsigned NOT NULL,
  `work_tag_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`works_id`,`tag_id`),
  KEY `idx_work_tag_tag` (`tag_id`),
  CONSTRAINT `fk_work_tag_tag` FOREIGN KEY (`tag_id`) REFERENCES `tag_work` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_work_tag_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_voices` (
  `works_id` bigint(20) unsigned NOT NULL,
  `voices_id` int(10) unsigned NOT NULL,
  `work_voices_quantity` int(11) NOT NULL DEFAULT 1,
  `work_voices_context` varchar(16) DEFAULT NULL COMMENT 'solo | ensemble',
  PRIMARY KEY (`works_id`,`voices_id`),
  KEY `idx_work_voices_voice` (`voices_id`),
  CONSTRAINT `fk_work_voices_voice` FOREIGN KEY (`voices_id`) REFERENCES `voices` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_work_voices_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `works` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `works_song_name` varchar(1024) DEFAULT NULL,
  `works_title` varchar(1024) DEFAULT NULL,
  `works_subtitle` text DEFAULT NULL,
  `works_attr_type` varchar(64) DEFAULT NULL COMMENT 'ANONIMA, TRADICIONAL, POPULAR, ATRIBUIDA',
  `works_attribution_note` varchar(255) DEFAULT NULL,
  `works_opus` varchar(255) DEFAULT NULL,
  `works_catalogue` varchar(255) DEFAULT NULL COMMENT 'identificador de catalogo correctamente formateado',
  `works_musical_key` varchar(255) DEFAULT NULL,
  `works_year` smallint(6) DEFAULT NULL,
  `works_epoch_id` int(10) unsigned DEFAULT NULL,
  `works_duration` varchar(64) DEFAULT NULL,
  `works_measures` int(11) DEFAULT NULL,
  `works_pages` int(11) DEFAULT NULL,
  `works_parts` int(11) DEFAULT NULL,
  `works_complexity` int(11) DEFAULT NULL,
  `works_description` text DEFAULT NULL,
  `works_license` varchar(128) DEFAULT NULL,
  `works_public_domain` tinyint(1) NOT NULL DEFAULT 0,
  `works_origin` varchar(255) DEFAULT NULL COMMENT 'proveedor/fuente o email si lo manda usuario',
  `works_origin_id` varchar(255) DEFAULT NULL COMMENT 'id del registro en ese origen',
  `works_type_file` int(11) DEFAULT NULL COMMENT 'FK futura a tabla de tipos de fichero',
  `works_obra_iden` bigint(20) unsigned DEFAULT NULL COMMENT 'autoreferencia works.id',
  `works_relative_path` varchar(1024) DEFAULT NULL,
  `works_music_digest` char(32) DEFAULT NULL,
  `works_key` varchar(64) DEFAULT NULL COMMENT 'hash de agrupación heredado (work_key)',
  `works_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `works_updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  `works_voicing` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `works_instrumentation` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_works_key` (`works_key`),
  KEY `idx_works_epoch` (`works_epoch_id`),
  KEY `idx_works_obra_iden` (`works_obra_iden`),
  CONSTRAINT `fk_works_epoch` FOREIGN KEY (`works_epoch_id`) REFERENCES `epochs` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_works_obra_iden` FOREIGN KEY (`works_obra_iden`) REFERENCES `works` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=366876 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `works_person_import` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `works_id` bigint(20) unsigned NOT NULL,
  `works_person_import_name` varchar(1024) NOT NULL,
  `works_person_import_role` varchar(16) NOT NULL COMMENT 'composer | artist',
  `works_person_import_source` varchar(32) NOT NULL DEFAULT '',
  `works_person_import_resolved` tinyint(1) NOT NULL DEFAULT 0,
  `works_person_import_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_wpi_work` (`works_id`),
  KEY `idx_wpi_name` (`works_person_import_name`(255)),
  KEY `idx_wpi_role` (`works_person_import_role`),
  CONSTRAINT `fk_wpi_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=506019 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `works_person_roles` (
  `works_person_roles_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `works_person_roles_work_id` bigint(20) unsigned NOT NULL,
  `works_person_roles_person_id` char(36) NOT NULL,
  `works_person_roles_role_id` int(11) NOT NULL,
  `works_person_roles_order` int(11) NOT NULL DEFAULT 0,
  `works_person_roles_attribution_type` varchar(64) DEFAULT NULL COMMENT 'ANONIMA, TRADICIONAL, POPULAR, ATRIBUIDA',
  PRIMARY KEY (`works_person_roles_id`),
  UNIQUE KEY `uq_works_person_roles` (`works_person_roles_work_id`,`works_person_roles_person_id`,`works_person_roles_role_id`),
  KEY `idx_wpr_work` (`works_person_roles_work_id`),
  KEY `idx_wpr_person` (`works_person_roles_person_id`),
  KEY `idx_wpr_role` (`works_person_roles_role_id`),
  CONSTRAINT `fk_wpr_person` FOREIGN KEY (`works_person_roles_person_id`) REFERENCES `persons` (`persons_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_wpr_role` FOREIGN KEY (`works_person_roles_role_id`) REFERENCES `roles` (`id`),
  CONSTRAINT `fk_wpr_work` FOREIGN KEY (`works_person_roles_work_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=352108 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

