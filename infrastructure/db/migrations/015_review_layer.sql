-- 015 · Capa de revisión humana: cola de trabajo + artefacto de decisiones.
--
-- NADA de esto aplica nada al catálogo: no escribe en `works_person_roles`, ni en `works`, ni en
-- `persons`. Es la capa donde la revisión decide, con claves LÓGICAS (independientes del entorno):
--
--   `review_items`      cola de trabajo DERIVADA (se refresca desde `import_person_parse`).
--                       Unidad de revisión por clúster de identidad, por obra (atribución) o por
--                       excepción (ambigüedad) — nunca por fila suelta salvo cuando es necesario.
--   `review_decisions`  artefacto de DECISIONES (append/update humano). Claves lógicas:
--                       `work_key` = `PDMX:<works_key>` | `CPDL:<origin_id>`
--                       `person_key` = ancla (`viaf:…`, `musicbrainz:…`) | `name:<normalizado>`
--                       `role_key` = clave canónica de rol (composer, arranger, adapter, …)
--                       Nada de `works.id` ni `persons_id` (UUID): eso lo resuelve, en cada
--                       entorno, el futuro programa de aplicación.
--
-- `decision_key` / `item_key` son concatenaciones canónicas no nulas: dan idempotencia sin
-- depender de que las columnas lógicas sean NULL.

CREATE TABLE IF NOT EXISTS `review_items` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `item_key` varchar(255) NOT NULL,
  `item_type` varchar(24) NOT NULL
    COMMENT 'identity_cluster|work_attribution|exception_ambiguous',
  `person_key` varchar(255) DEFAULT NULL,
  `work_key` varchar(255) DEFAULT NULL,
  `role_key` varchar(32) DEFAULT NULL,
  `attribution_status` varchar(16) DEFAULT NULL,
  `filas` int(10) unsigned NOT NULL DEFAULT 0,
  `obras` int(10) unsigned NOT NULL DEFAULT 0,
  `roles` varchar(255) DEFAULT NULL,
  `estados` varchar(255) DEFAULT NULL,
  `candidatos_json` longtext DEFAULT NULL,
  `contexto_json` longtext DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `updated_at` datetime(6) NOT NULL DEFAULT current_timestamp(6) ON UPDATE current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_review_item` (`item_key`),
  KEY `idx_review_item_type` (`item_type`),
  KEY `idx_review_item_person` (`person_key`),
  KEY `idx_review_item_work` (`work_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `review_decisions` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `decision_key` varchar(255) NOT NULL,
  `item_key` varchar(255) DEFAULT NULL,
  `decision_type` varchar(24) NOT NULL COMMENT 'identity|relation|attribution',
  `person_key` varchar(255) DEFAULT NULL,
  `work_key` varchar(255) DEFAULT NULL,
  `role_key` varchar(32) DEFAULT NULL,
  `decision` varchar(24) NOT NULL
    COMMENT 'accept|reject|uncertain|create_person|map_to_existing|not_a_person|leave_unresolved',
  `target_person_key` varchar(255) DEFAULT NULL,
  `attribution_status` varchar(16) DEFAULT NULL,
  `evidence_json` longtext DEFAULT NULL,
  `notes` varchar(512) DEFAULT NULL,
  `decided_by` varchar(128) DEFAULT NULL,
  `decided_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  `batch` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_review_decision` (`decision_key`),
  KEY `idx_review_decision_type` (`decision_type`),
  KEY `idx_review_decision_person` (`person_key`),
  KEY `idx_review_decision_work` (`work_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Guarda: las dos tablas deben existir con sus columnas clave.
SET @rev_ok := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND ((table_name = 'review_items' AND column_name IN ('item_key', 'item_type', 'person_key', 'work_key'))
      OR (table_name = 'review_decisions' AND column_name IN ('decision_key', 'decision_type', 'decision', 'target_person_key')))
);
SET @rev_sql := IF(
  @rev_ok = 8,
  'DO 0',
  'SELECT * FROM `__migracion_015_abortada__capa_de_revision_incompleta`'
);
PREPARE rev_stmt FROM @rev_sql;
EXECUTE rev_stmt;
DEALLOCATE PREPARE rev_stmt;
