CREATE TABLE IF NOT EXISTS works (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    work_key VARCHAR(64) NULL,
    composer VARCHAR(1024) NULL,
    title VARCHAR(1024) NULL,
    genre VARCHAR(255) NULL,
    opus VARCHAR(255) NULL,
    catalogue VARCHAR(255) NULL,
    musical_key VARCHAR(255) NULL,
    year SMALLINT NULL,
    instrumentation VARCHAR(255) NULL,
    language VARCHAR(64) NULL,
    tags TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_works_work_key (work_key),
    KEY idx_works_composer_title (composer(255), title(255))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

ALTER TABLE archive_entries
    ADD COLUMN work_id BIGINT UNSIGNED NULL AFTER title;

CREATE INDEX idx_archive_entries_work ON archive_entries (work_id);

ALTER TABLE archive_entries
    ADD CONSTRAINT fk_archive_entries_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE SET NULL;
