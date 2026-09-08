-- 034_works_music_digest.sql
-- "Número mágico" de contenido musical: hash md5 de las notas normalizadas
-- (step/octave/duration/voice) extraídas del MusicXML. Permite agrupar obras
-- equivalentes entre ediciones distintas sin comparar texto. Lo rellena
-- scripts/analyze_works_content.py (offline, sin R2).

ALTER TABLE works
    ADD COLUMN music_digest CHAR(32) NULL AFTER work_key;

CREATE INDEX idx_works_music_digest ON works (music_digest);
