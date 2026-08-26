-- 030_authority_sync_state.sql
-- Checkpoint de sincronización de fuentes de autoridad externas (Metabrainz/MusicBrainz,
-- y futuras VIAF/IMSLP). Cada fila guarda el último paquete procesado por fuente, para
-- que el job diario continúe desde donde se quedó (idempotente e interrumpible).

CREATE TABLE IF NOT EXISTS authority_sync_state (
    source VARCHAR(32) NOT NULL,          -- metabrainz | viaf | imslp | wikidata
    last_packet BIGINT UNSIGNED NOT NULL DEFAULT 0,  -- último paquete/revisión procesado
    last_success_at DATETIME(6) NULL,
    last_error VARCHAR(512) NULL,
    metadata_json JSON NULL,
    PRIMARY KEY (source)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
