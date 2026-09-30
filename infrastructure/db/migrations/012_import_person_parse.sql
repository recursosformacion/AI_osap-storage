-- 012 · Staging del re-parse de `works_person_import` (persona+rol y atribuciones).
--
-- Resultado del parser determinista (`application/services/import_person_parser.py` +
-- `scripts/parse_import_persons.py`). Es una tabla de TRABAJO: no escribe en `works_person_roles`
-- ni en `works`; alimenta la revisión y el futuro artefacto de aplicación.
--
--   kind='person'      -> persona propuesta con `role_id` (puede venir de origen o de humano)
--   kind='attribution' -> atribución no personal del texto (`anonymous`/`traditional`)
--   kind='junk'        -> valor sin autoría; se conserva para auditoría del parser
--
-- `person_id` solo se rellena si el nombre resuelve a una persona EXISTENTE del catálogo
-- (reglas canónicas). Nunca se crean personas aquí.

CREATE TABLE IF NOT EXISTS `import_person_parse` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `works_id` bigint(20) unsigned NOT NULL,
  `import_row_id` bigint(20) unsigned DEFAULT NULL,
  `kind` varchar(16) NOT NULL COMMENT 'person|attribution|junk',
  `person_name_raw` varchar(512) DEFAULT NULL,
  `person_name_norm` varchar(191) DEFAULT NULL,
  `role_key` varchar(32) NOT NULL DEFAULT '' COMMENT 'clave canónica o vacío en atribuciones',
  `role_id` int(11) DEFAULT NULL,
  `attribution_status` varchar(16) DEFAULT NULL COMMENT 'anonymous|traditional',
  `person_id` char(36) DEFAULT NULL COMMENT 'solo si resuelve a persona existente',
  `source` varchar(16) NOT NULL COMMENT 'pdmx|cpdl',
  `evidence_json` longtext DEFAULT NULL,
  `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending|resolved|new_person|rejected|applied',
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ipp_work_role_name` (`works_id`, `role_key`, `person_name_norm`),
  KEY `idx_ipp_person` (`person_id`),
  KEY `idx_ipp_status` (`status`),
  KEY `idx_ipp_kind` (`kind`),
  KEY `idx_ipp_work` (`works_id`),
  CONSTRAINT `fk_ipp_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ipp_person` FOREIGN KEY (`person_id`) REFERENCES `persons` (`persons_id`) ON DELETE SET NULL,
  CONSTRAINT `fk_ipp_role` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Comprobación: si la tabla preexistía con otro esquema, abortar en vez de registrar la migración.
SET @ipp_cols := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'import_person_parse'
    AND column_name IN ('works_id', 'kind', 'role_key', 'attribution_status', 'person_id', 'status')
);
SET @ipp_sql := IF(
  @ipp_cols = 6,
  'DO 0',
  'SELECT * FROM `__migracion_012_abortada__import_person_parse_con_esquema_inesperado`'
);
PREPARE ipp_stmt FROM @ipp_sql;
EXECUTE ipp_stmt;
DEALLOCATE PREPARE ipp_stmt;
