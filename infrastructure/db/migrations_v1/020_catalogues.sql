-- Catálogos musicales (catálogos temáticos por compositor).
-- Permite identificar el catálogo de una obra por prefijo/sigla o por compositor,
-- y usar el catálogo como pista de compositor en la limpieza.

CREATE TABLE IF NOT EXISTS catalogues (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prefix VARCHAR(16) NOT NULL,
    composer VARCHAR(255) NOT NULL,
    catalogue_name VARCHAR(255) NOT NULL,
    creator VARCHAR(255) NOT NULL,
    ordering_criterion VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_catalogues_prefix (prefix),
    KEY idx_catalogues_composer (composer(191))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
