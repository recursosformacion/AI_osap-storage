-- Evidencia de creación de compositores automáticos (trazabilidad de extracción).
-- Conserva la obra que provocó la creación, los datos extraídos y el origen.
-- La evidencia NO se borra tras una fusión: se redirige al compositor destino.

CREATE TABLE IF NOT EXISTS composer_creation_evidence (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    composer_id CHAR(36) NOT NULL,
    work_id BIGINT UNSIGNED NULL,
    work_title VARCHAR(1024) NULL,
    extracted_author VARCHAR(1024) NULL,
    provider VARCHAR(255) NULL,
    resource_reference VARCHAR(1024) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_cce_composer (composer_id),
    KEY idx_cce_work (work_id),
    CONSTRAINT fk_cce_composer FOREIGN KEY (composer_id) REFERENCES composers (id) ON DELETE CASCADE,
    CONSTRAINT fk_cce_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE SET NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
