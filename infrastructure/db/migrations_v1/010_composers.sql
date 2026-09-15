CREATE TABLE IF NOT EXISTS composers (
    id CHAR(36) NOT NULL,
    name VARCHAR(1024) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_composers_name (name(255))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS composer_aliases (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    composer_id CHAR(36) NOT NULL,
    alias VARCHAR(1024) NOT NULL,
    normalized_alias VARCHAR(1024) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_composer_aliases_normalized (normalized_alias(255)),
    KEY idx_composer_aliases_composer (composer_id),
    CONSTRAINT fk_composer_aliases_composer FOREIGN KEY (composer_id) REFERENCES composers (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
