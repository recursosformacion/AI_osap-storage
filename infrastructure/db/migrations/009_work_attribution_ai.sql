-- 009 · Atribución asistida por IA: propuestas y auditoría de asignaciones.
--
-- `work_person_ai_proposals` guarda HIPÓTESIS (nunca escribe en works_person_roles).
-- `work_attribution_history` audita las asignaciones efectivas y permite revertir:
--   sabe exactamente qué relación se creó a partir de qué propuesta (proposal_id).

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

CREATE TABLE IF NOT EXISTS `work_attribution_history` (
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
  KEY `idx_wah_work` (`work_id`),
  KEY `idx_wah_person` (`person_id`),
  KEY `idx_wah_proposal` (`proposal_id`),
  CONSTRAINT `fk_wah_work` FOREIGN KEY (`work_id`) REFERENCES `works` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_wah_person` FOREIGN KEY (`person_id`) REFERENCES `persons` (`persons_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_wah_role` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
