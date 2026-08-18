-- 027_composer_candidate.sql
-- Candidatos a Composer (fase de limpieza/priorización).
-- Resultado de clasificar las atribuciones 'unknown' de composer_identity_resolution:
-- se etiquetan (real | review | mojibake | no_persona | qualifier) para decidir qué se
-- resuelve con identity-resolver y qué se descarta (mojibake/no_persona no crean Composer).
-- `verdict` viene de classify_composer_name (correct|not_reviewed|incorrect).

CREATE TABLE IF NOT EXISTS composer_candidate (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    attribution VARCHAR(1024) NOT NULL,
    name_key VARCHAR(128) NOT NULL,
    cleaned_name VARCHAR(1024) NULL,
    work_count INT NOT NULL DEFAULT 0,
    label VARCHAR(32) NOT NULL,
    verdict VARCHAR(16) NOT NULL,
    resolved_status VARCHAR(32) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_cc_attribution (attribution(255)),
    KEY idx_cc_name_key (name_key),
    KEY idx_cc_label (label),
    KEY idx_cc_work_count (work_count)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
