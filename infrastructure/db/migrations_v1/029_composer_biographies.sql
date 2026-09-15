-- 029_composer_biographies.sql
-- Biografías de compositores (enriquecimiento generado por IA / web).
-- El script scripts/composer_review_ai.py la crea si no existe. Se formaliza aquí
-- para que exista también en despliegues que solo aplican migraciones.

CREATE TABLE IF NOT EXISTS composer_biographies (
    composer_id CHAR(36) PRIMARY KEY,
    biography_summary TEXT,
    biography_era TEXT,
    biography_nationality TEXT,
    biography_key_works JSON,
    biography_key_fact TEXT,
    biography_references JSON,
    biography_updated_at VARCHAR(64),
    CONSTRAINT fk_composer_bio FOREIGN KEY (composer_id) REFERENCES composers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
