-- Enriquecimiento de metadatos de works (fuente: CSV + JSON MuseScore)
ALTER TABLE works
    ADD COLUMN subtitle VARCHAR(1024) NULL AFTER title,
    ADD COLUMN artist VARCHAR(1024) NULL AFTER composer,
    ADD COLUMN song_name VARCHAR(1024) NULL AFTER artist,
    ADD COLUMN duration VARCHAR(64) NULL,
    ADD COLUMN measures INT NULL,
    ADD COLUMN pages INT NULL,
    ADD COLUMN parts INT NULL,
    ADD COLUMN complexity INT NULL,
    ADD COLUMN license VARCHAR(128) NULL,
    ADD COLUMN public_domain TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN description TEXT NULL,
    ADD COLUMN thumbnails TEXT NULL;

CREATE TABLE IF NOT EXISTS work_tags (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    work_id BIGINT UNSIGNED NOT NULL,
    tag VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_work_tags (work_id, tag),
    KEY idx_work_tags_tag (tag),
    CONSTRAINT fk_work_tags_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS work_genres (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    work_id BIGINT UNSIGNED NOT NULL,
    genre VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_work_genres (work_id, genre),
    KEY idx_work_genres_genre (genre),
    CONSTRAINT fk_work_genres_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS work_instruments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    work_id BIGINT UNSIGNED NOT NULL,
    instrument VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_work_instruments (work_id, instrument),
    CONSTRAINT fk_work_instruments_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS work_parts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    work_id BIGINT UNSIGNED NOT NULL,
    part_name VARCHAR(255) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_work_parts (work_id, part_name),
    CONSTRAINT fk_work_parts_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
