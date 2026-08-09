-- Administración de compositores: estado, merged_into, historial de fusiones y
-- persistencia de composer_id en Works (Storage es propietario de la relación Work -> composer).

ALTER TABLE composers
    ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active' AFTER name,
    ADD COLUMN merged_into CHAR(36) NULL AFTER status,
    ADD COLUMN merged_at DATETIME(6) NULL AFTER merged_into;

CREATE INDEX idx_composers_status ON composers (status);
CREATE INDEX idx_composers_merged_into ON composers (merged_into);

ALTER TABLE works
    ADD COLUMN composer_id CHAR(36) NULL AFTER composer;

CREATE INDEX idx_works_composer_id ON works (composer_id);

CREATE TABLE IF NOT EXISTS composer_merge_history (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    merge_operation_id CHAR(36) NULL,
    source_composer_id CHAR(36) NOT NULL,
    target_composer_id CHAR(36) NOT NULL,
    merged_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    merged_by VARCHAR(255) NULL,
    PRIMARY KEY (id),
    KEY idx_cmh_source (source_composer_id),
    KEY idx_cmh_target (target_composer_id),
    KEY idx_cmh_operation (merge_operation_id),
    CONSTRAINT fk_cmh_source FOREIGN KEY (source_composer_id) REFERENCES composers (id) ON DELETE RESTRICT,
    CONSTRAINT fk_cmh_target FOREIGN KEY (target_composer_id) REFERENCES composers (id) ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
