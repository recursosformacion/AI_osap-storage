-- Cache local de resultados de MusicBrainz (para procesar sin rate limit del API)

CREATE TABLE IF NOT EXISTS musicbrainz_cache (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    query_key VARCHAR(255) NOT NULL,
    payload MEDIUMTEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_mb_cache_query (query_key)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
