-- Metadatos extraidos de ficheros MusicXML/MXL. Una representacion puede tener un MXL
-- concreto y sus datos editoriales; no se guardan en works porque son de la representacion.
CREATE TABLE IF NOT EXISTS representation_metadata (
    representation_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    xml_title VARCHAR(512) NULL,
    instrumentation JSON NULL,
    ensemble VARCHAR(128) NULL,
    parts_count INT NULL,
    measures INT NULL,
    notes INT NULL,
    musical_keys JSON NULL,
    time_signatures JSON NULL,
    tempo VARCHAR(32) NULL,
    has_lyrics TINYINT(1) NULL,
    creators JSON NULL,
    source VARCHAR(512) NULL,
    rights VARCHAR(512) NULL,
    software VARCHAR(128) NULL,
    encoding_date VARCHAR(32) NULL,
    raw JSON NULL,
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_rep_metadata_representation
        FOREIGN KEY (representation_id) REFERENCES representations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

