-- 035_cpdl_pages.sql
-- Tabla de páginas CPDL ingeridas (fuente externa de identidad/metadatos).
-- NO forma parte del catálogo `works`: es corpus de referencia para fusión/
-- identidad y comparación. La rellena scripts/import_cpdl_pages.py a partir de
-- exports MediaWiki (Special:Export) de ChoralWiki.

CREATE TABLE IF NOT EXISTS cpdl_pages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    page_title VARCHAR(512) NOT NULL,
    title VARCHAR(1024) NULL,
    composer VARCHAR(1024) NULL,
    catalogue_hint VARCHAR(255) NULL,
    arrangement_hint TINYINT(1) NOT NULL DEFAULT 0,
    voicing TEXT NULL,
    instrumentation TEXT NULL,
    genre TEXT NULL,
    language TEXT NULL,
    license VARCHAR(255) NULL,
    n_editions INT NOT NULL DEFAULT 0,
    payload_json LONGTEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_cpdl_pages_title (page_title(255)),
    KEY idx_cpdl_composer (composer(255)),
    KEY idx_cpdl_catalogue (catalogue_hint)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
