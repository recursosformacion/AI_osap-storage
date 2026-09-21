-- 004: historial de limpieza de personas (todo cambio de ficha es reversible).
-- Guarda los valores previos y el batch para poder revertir una pasada de limpieza.
CREATE TABLE IF NOT EXISTS persons_cleanup_history (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    persons_id CHAR(36) NOT NULL,
    batch_id VARCHAR(64) NOT NULL,
    prev_name VARCHAR(1024),
    new_name VARCHAR(1024),
    prev_givenname VARCHAR(512),
    prev_familyname VARCHAR(512),
    prev_sortname VARCHAR(1024),
    prev_birth_year VARCHAR(16),
    prev_death_year VARCHAR(16),
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_pch_person (persons_id),
    KEY idx_pch_batch (batch_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
