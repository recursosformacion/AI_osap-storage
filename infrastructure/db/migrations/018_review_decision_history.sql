-- 018 · Historial append-only de decisiones de revisión.
--
-- Regla: **nunca desaparece una decisión humana que alguna vez fue registrada**. `review_decisions`
-- guarda la decisión vigente por unidad; `review_decision_history` guarda cada corrección (la
-- anterior y la nueva), con motivo, quién y cuándo. Corregir es: insertar historial (append-only) y
-- actualizar la fila vigente por el mecanismo del motor (nunca un UPDATE suelto).

CREATE TABLE IF NOT EXISTS `review_decision_history` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `decision_key` varchar(255) NOT NULL,
  `operation` varchar(16) NOT NULL COMMENT 'correct',
  `previous_decision` varchar(24) DEFAULT NULL,
  `new_decision` varchar(24) NOT NULL,
  `reason` varchar(512) DEFAULT NULL,
  `evidence_json` longtext DEFAULT NULL,
  `decided_by` varchar(128) DEFAULT NULL,
  `decided_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_rdh_key` (`decision_key`),
  KEY `idx_rdh_fecha` (`decided_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @rdh_ok := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'review_decision_history'
    AND column_name IN ('decision_key', 'previous_decision', 'new_decision', 'reason', 'decided_by')
);
SET @rdh_sql := IF(
  @rdh_ok = 5,
  'DO 0',
  'SELECT * FROM `__migracion_018_abortada__review_decision_history_incompleta`'
);
PREPARE rdh_stmt FROM @rdh_sql;
EXECUTE rdh_stmt;
DEALLOCATE PREPARE rdh_stmt;
