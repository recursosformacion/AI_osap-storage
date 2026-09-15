CREATE TABLE IF NOT EXISTS archives (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(512) NOT NULL,
    url VARCHAR(2048) NULL,
    local_path VARCHAR(1024) NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'imported',
    size BIGINT NULL,
    sha256 CHAR(64) NULL,
    downloaded_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_archives_name (name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS archive_entries (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    archive_id BIGINT UNSIGNED NOT NULL,
    logical_id VARCHAR(255) NULL,
    relative_path VARCHAR(1024) NOT NULL,
    file_id BIGINT UNSIGNED NULL,
    size BIGINT NULL,
    offset_bytes BIGINT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'missing',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_archive_entries (archive_id, relative_path),
    KEY idx_archive_entries_archive (archive_id),
    KEY idx_archive_entries_logical (logical_id),
    KEY idx_archive_entries_file (file_id),
    KEY idx_archive_entries_status (status),
    CONSTRAINT fk_archive_entries_archive FOREIGN KEY (archive_id) REFERENCES archives (id) ON DELETE CASCADE,
    CONSTRAINT fk_archive_entries_file FOREIGN KEY (file_id) REFERENCES files (id) ON DELETE SET NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
