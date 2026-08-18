-- Identificadores de autoridad asociados a entidades (obra o compositor).
-- No es una copia de las bases de autoridad: son los IDs (con proveniencia) que el
-- sistema consume. entity_id es genérico (work o composer), por eso no hay FK única.

CREATE TABLE IF NOT EXISTS authority_identifiers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    entity_type VARCHAR(16) NOT NULL,             -- work | composer
    entity_id VARCHAR(255) NOT NULL,
    scheme VARCHAR(24) NOT NULL,                  -- wikidata|isni|viaf|lccn|musicbrainz|iswc|ipi
    value VARCHAR(255) NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT '',
    confidence DECIMAL(5,4) NOT NULL DEFAULT 0,
    metadata_json JSON NULL,
    retrieved_at DATETIME(6) NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_authority (entity_type, entity_id, scheme),
    KEY idx_authority_scheme_value (scheme, value)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
