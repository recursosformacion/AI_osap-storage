-- 011 · Revisión humana de la atribución IA: decisiones completas por obra.
--
-- Dos capas separadas (no se mezclan):
--   1. `work_ai_reviews`: la decisión de ATRIBUCIÓN de la obra (identified/anonymous/traditional/
--      unknown) + nota + evidencia + contradicciones + el contexto congelado que vio el modelo.
--   2. `work_ai_review_relations`: las PERSONAS RELACIONADAS (persona × rol) con su decisión
--      (`pending|accepted|rejected|uncertain`) y su origen (`gemini|existing|human`).
--
-- Una obra anónima o tradicional puede tener arreglista: esta capa es independiente de la
-- atribución. NINGUNA de estas tablas escribe en `works_person_roles`; son el artefacto de
-- decisiones que después aplicará (idéntico) el programa de Fase 6 en Dev y Prod.
--
-- Las comprobaciones finales abortan si el esquema no es el esperado (igual que 009).

CREATE TABLE IF NOT EXISTS `work_ai_reviews` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `work_id` bigint(20) unsigned NOT NULL,
  `batch_id` varchar(64) DEFAULT NULL,
  `attribution_status` varchar(16) NOT NULL COMMENT 'identified|anonymous|traditional|unknown',
  `attribution_note` varchar(512) DEFAULT NULL,
  `attribution_confidence` decimal(4,3) DEFAULT NULL,
  `contradictions_json` longtext DEFAULT NULL,
  `context_json` longtext DEFAULT NULL,
  `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending|reviewed',
  `reviewed_by` varchar(128) DEFAULT NULL,
  `reviewed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_war_work` (`work_id`),
  KEY `idx_war_status` (`status`),
  CONSTRAINT `fk_war_work` FOREIGN KEY (`work_id`) REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `work_ai_review_relations` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `review_id` bigint(20) unsigned NOT NULL,
  `work_id` bigint(20) unsigned NOT NULL,
  `person_id` char(36) DEFAULT NULL,
  `person_name_raw` varchar(512) NOT NULL,
  `person_name_norm` varchar(191) NOT NULL,
  `role_id` int(11) NOT NULL,
  `decision` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending|accepted|rejected|uncertain',
  `origin` varchar(16) NOT NULL DEFAULT 'gemini' COMMENT 'gemini|existing|human',
  `confidence` decimal(4,3) DEFAULT NULL,
  `evidence_json` longtext DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_warr_review_role_name` (`review_id`, `role_id`, `person_name_norm`),
  KEY `idx_warr_work` (`work_id`),
  KEY `idx_warr_person` (`person_id`),
  KEY `idx_warr_decision` (`decision`),
  CONSTRAINT `fk_warr_review` FOREIGN KEY (`review_id`) REFERENCES `work_ai_reviews` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_warr_work` FOREIGN KEY (`work_id`) REFERENCES `works` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_warr_person` FOREIGN KEY (`person_id`) REFERENCES `persons` (`persons_id`) ON DELETE SET NULL,
  CONSTRAINT `fk_warr_role` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Comprobación A: `work_ai_reviews` con las columnas esperadas.
SET @war_cols := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_ai_reviews'
    AND column_name IN ('work_id', 'attribution_status', 'contradictions_json', 'context_json', 'status')
);
SET @war_sql := IF(
  @war_cols = 5,
  'DO 0',
  'SELECT * FROM `__migracion_011_abortada__work_ai_reviews_con_esquema_inesperado`'
);
PREPARE war_stmt FROM @war_sql;
EXECUTE war_stmt;
DEALLOCATE PREPARE war_stmt;

-- Comprobación B: `work_ai_review_relations` con las columnas esperadas.
SET @warr_cols := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'work_ai_review_relations'
    AND column_name IN ('review_id', 'person_id', 'role_id', 'decision', 'origin', 'confidence')
);
SET @warr_sql := IF(
  @warr_cols = 6,
  'DO 0',
  'SELECT * FROM `__migracion_011_abortada__work_ai_review_relations_con_esquema_inesperado`'
);
PREPARE warr_stmt FROM @warr_sql;
EXECUTE warr_stmt;
DEALLOCATE PREPARE warr_stmt;
