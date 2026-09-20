-- Completa el índice EXTERNO de fuentes RISM (no toca el catálogo propio).
-- Aplicar tras scripts/migrate_rism_sources.sql. Idempotente.

ALTER TABLE rism_sources
  ADD COLUMN IF NOT EXISTS rism_source_type varchar(120) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS rism_subjects varchar(1000) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS rism_notes varchar(2000) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS rism_institution_id varchar(32) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS rism_standard_title_id varchar(32) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS rism_other_persons varchar(1000) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS rism_incipit_count int(11) NOT NULL DEFAULT 0;

-- Enlaces de la fuente (MARC 856): copias digitalizadas u otros recursos externos.
CREATE TABLE IF NOT EXISTS `rism_source_links` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `rism_source_id` varchar(32) NOT NULL,
  `rism_source_links_url` varchar(1024) NOT NULL,
  `rism_source_links_note` varchar(255) DEFAULT NULL,
  `rism_source_links_ind1` char(1) DEFAULT NULL,
  `rism_source_links_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_rism_source_links_source` (`rism_source_id`),
  KEY `idx_rism_source_links_url` (`rism_source_links_url`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
