-- Autoridad de compositores (índice de identidad) — independiente del Maestro.
-- 023_composer_authority.sql
--
-- Dos conceptos separados:
--   * composer_authority       : personas que sabemos que son compositores (autoridad
--     externa, p. ej. Wikidata). Sirve para IDENTIFICAR a una persona, no para publicarla.
--   * composer_authority_names : variantes de nombre (aliases) por autoridad, enriquecible
--     sin modificar la entidad principal.
--
-- El Maestro `composers` queda intacto: solo se crea un Composer cuando se decide
-- incorporarlo (resolver con identidad sólida).

CREATE TABLE IF NOT EXISTS composer_authority (
    authority_id  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    wikidata_id   VARCHAR(16),
    viaf_id       VARCHAR(32),
    imslp_id      VARCHAR(255),
    canonical_name VARCHAR(255) NOT NULL,
    birth_date    VARCHAR(20),
    death_date    VARCHAR(20),
    PRIMARY KEY (authority_id),
    KEY idx_ca_wikidata (wikidata_id),
    KEY idx_ca_viaf (viaf_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS composer_authority_names (
    authority_id  BIGINT UNSIGNED NOT NULL,
    name          VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(128) NOT NULL,
    source        VARCHAR(32) NOT NULL DEFAULT 'wikidata',
    KEY idx_can_normalized (normalized_name),
    KEY idx_can_authority (authority_id),
    CONSTRAINT fk_can_authority FOREIGN KEY (authority_id)
        REFERENCES composer_authority(authority_id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
