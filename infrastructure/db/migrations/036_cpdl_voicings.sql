-- 036_cpdl_voicings.sql
-- Términos de voicing derivados de cpdl_pages.voicing para búsqueda por voicing.
-- Estructura de búsqueda auxiliar: NO crea nuevas obras ni nuevas identidades.
-- Cada fila relaciona una página CPDL (única) con UN término normalizado buscable;
-- una página con "SATB, STTB, AATB, ATTB" tiene 4 filas (SATB/STTB/AATB/ATTB),
-- nunca 4 obras. La rellena scripts/import_cpdl_pages.py (y backfill_cpdl_voicings.py).

CREATE TABLE IF NOT EXISTS cpdl_voicings (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    cpdl_page_id BIGINT UNSIGNED NOT NULL,
    term VARCHAR(64) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_cpdl_voicing (cpdl_page_id, term),
    KEY idx_cpdl_voicing_term (term),
    CONSTRAINT fk_cpdl_voicings_page FOREIGN KEY (cpdl_page_id)
        REFERENCES cpdl_pages (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
