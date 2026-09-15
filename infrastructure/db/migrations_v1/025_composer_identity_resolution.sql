-- 025_composer_identity_resolution.sql
-- Persistencia de la resolución de identidad escalonada (evidencia acumulada).
-- Cada obra → una fila con el estado, la razón de la decisión y la evidencia JSON
-- (cómo se llegó a ella). Operativo sin JSONL.
--
-- NOTA: se llama `composer_identity_resolution` (no `composer_resolution`) porque ese
-- nombre ya lo usa la auditoría de recuperación (021_composer_recovery.sql).

CREATE TABLE IF NOT EXISTS composer_identity_resolution (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    test_id VARCHAR(64) NOT NULL,
    work_id BIGINT NOT NULL,
    attribution VARCHAR(255),
    status VARCHAR(32) NOT NULL,
    decision_reason VARCHAR(255),
    evidence_json JSON NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_cir_test (test_id),
    KEY idx_cir_work (work_id),
    UNIQUE KEY uq_cir_test_work (test_id, work_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
