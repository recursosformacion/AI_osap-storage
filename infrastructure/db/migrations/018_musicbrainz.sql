-- Integracion con MusicBrainz: id del artista para trazabilidad y disambiguacion

ALTER TABLE composers
    ADD COLUMN musicbrainz_id VARCHAR(36) NULL AFTER name;

CREATE INDEX idx_composers_musicbrainz ON composers (musicbrainz_id);
