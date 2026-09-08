-- 031_composer_homepage.sql
-- Añade la página web / homepage del compositor (mantenimiento administrativo).
-- Se expone en el mantenimiento funcional de compositores (update_composer).

ALTER TABLE composers
    ADD COLUMN homepage VARCHAR(1024) NULL AFTER name;

CREATE INDEX idx_composers_homepage ON composers (homepage(255));
