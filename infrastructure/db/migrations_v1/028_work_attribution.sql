-- 028_work_attribution.sql
-- Atribución de la obra: campo de tipo (ANONIMA/TRADICIONAL/POPULAR/ATRIBUIDA o libre)
-- y texto de la atribución (ej. "Traditional English"). Permite no forzar la atribución
-- no-persona dentro de works.composer y buscarla junto al resto de campos.

ALTER TABLE works
    ADD COLUMN attribution_type VARCHAR(64) NULL AFTER composer_id,
    ADD COLUMN attribution_note VARCHAR(255) NULL AFTER attribution_type;

CREATE INDEX idx_works_attribution_type ON works (attribution_type);
