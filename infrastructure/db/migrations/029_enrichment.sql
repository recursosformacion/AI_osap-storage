-- 029_enrichment.sql - staging y auditoria de enriquecimiento multifuente

CREATE TABLE IF NOT EXISTS `enrichment_candidates` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `entity_type` varchar(16) NOT NULL,
  `entity_key` varchar(255) NOT NULL,
  `field` varchar(64) NOT NULL,
  `value` text NOT NULL,
  `value_hash` char(64) NOT NULL,
  `source` varchar(32) NOT NULL,
  `evidence_url` varchar(1024) NOT NULL DEFAULT '',
  `confidence` decimal(3,2) NOT NULL DEFAULT 0.00,
  `license` varchar(64) NOT NULL DEFAULT '',
  `status` varchar(16) NOT NULL DEFAULT 'new',
  `fetched_at` datetime NOT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_enrich` (`entity_type`,`entity_key`,`field`,`source`,`value_hash`),
  KEY `idx_enrich_entity` (`entity_type`,`entity_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `enrichment_applied` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `entity_type` varchar(16) NOT NULL,
  `entity_key` varchar(255) NOT NULL,
  `field` varchar(64) NOT NULL,
  `old_value` text DEFAULT NULL,
  `new_value` text NOT NULL,
  `source` varchar(32) NOT NULL,
  `applied_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_applied_entity` (`entity_type`,`entity_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
