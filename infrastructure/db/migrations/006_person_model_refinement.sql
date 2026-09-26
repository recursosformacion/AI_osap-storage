-- 006: nuevas columnas para el modelo Person concretizado.
-- Añade nationality, image_url, person_type y attribution_note a `persons`;
-- y confidence/retrieved_at a `persons_identity` para trazabilidad de identificadores.
--
-- Idempotente: `IF NOT EXISTS` (MariaDB) evita errores si ya se aplicó.
-- NO registrar aquí en `schema_migrations`: lo hace el runner (`infrastructure/db/migrate.py`).

-- persons: campos para tipos de atribución y metadatos de autoridad.
ALTER TABLE persons
    ADD COLUMN IF NOT EXISTS persons_nationality VARCHAR(128) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS persons_image_url VARCHAR(2048) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS persons_type VARCHAR(32) NOT NULL DEFAULT 'person'
        COMMENT 'person|anonymous|traditional|pseudonym|corporate',
    ADD COLUMN IF NOT EXISTS persons_attribution_note VARCHAR(255) DEFAULT NULL;

ALTER TABLE persons
    ADD INDEX IF NOT EXISTS idx_persons_type (persons_type);

-- persons_identity: confianza y marca de tiempo de recuperación.
ALTER TABLE persons_identity
    ADD COLUMN IF NOT EXISTS identity_confidence FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS identity_retrieved_at DATETIME(6) DEFAULT NULL;

