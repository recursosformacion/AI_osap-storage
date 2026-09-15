-- Recuperación de identidad de compositores: marcado de sospechosos y trazabilidad.

ALTER TABLE composers
    ADD COLUMN suspicious TINYINT(1) NOT NULL DEFAULT 0 AFTER review_status,
    ADD COLUMN suspicious_reason VARCHAR(64) NULL AFTER suspicious;

CREATE TABLE IF NOT EXISTS composer_resolution (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    work_id BIGINT UNSIGNED NOT NULL,
    old_composer_id CHAR(36) NULL,
    candidate_composer_id CHAR(36) NULL,
    reason VARCHAR(64) NOT NULL,
    evidence TEXT NULL,
    confidence DECIMAL(5,4) NOT NULL DEFAULT 0,
    resolver_version VARCHAR(32) NOT NULL,
    decision VARCHAR(16) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_cr_work (work_id),
    KEY idx_cr_candidate (candidate_composer_id),
    CONSTRAINT fk_cr_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE,
    CONSTRAINT fk_cr_candidate FOREIGN KEY (candidate_composer_id) REFERENCES composers (id) ON DELETE SET NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
