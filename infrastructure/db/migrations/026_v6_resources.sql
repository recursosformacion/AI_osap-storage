-- V6 — Resource hijo directo de Work y File con clave física opaca.
-- Aditivo: no retira Representation ni works_resources; el corte se hará en la migración V6.

CREATE TABLE IF NOT EXISTS resources (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    work_id BIGINT UNSIGNED NOT NULL,
    kind VARCHAR(32) NOT NULL DEFAULT 'score',
    title VARCHAR(255) NULL,
    source_system VARCHAR(64) NULL,
    external_id VARCHAR(255) NULL,
    external_url VARCHAR(1024) NULL,
    license VARCHAR(255) NULL,
    rights_holder VARCHAR(255) NULL,
    is_reference TINYINT(1) NOT NULL DEFAULT 0,
    visibility VARCHAR(16) NOT NULL DEFAULT 'public',
    metadata_json JSON NULL,
    created_by VARCHAR(64) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_resources_work (work_id),
    KEY idx_resources_source (source_system, external_id),
    CONSTRAINT fk_resources_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- La clave física se copia literalmente desde R2; no se deriva del SHA-256.
ALTER TABLE files
    ADD COLUMN resource_id BIGINT UNSIGNED NULL,
    ADD COLUMN storage_key VARCHAR(1024) NULL,
    ADD KEY idx_files_resource (resource_id),
    ADD CONSTRAINT fk_files_resource FOREIGN KEY (resource_id)
        REFERENCES resources (id) ON DELETE SET NULL;
