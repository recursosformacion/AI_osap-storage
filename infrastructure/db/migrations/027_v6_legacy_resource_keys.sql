-- V6 — correspondencia de IDs de origen para Resources.
-- Permite que el mapeo sea idempotente y conserva la trazabilidad del corte.

ALTER TABLE resources
    ADD COLUMN legacy_kind VARCHAR(32) NULL,
    ADD COLUMN legacy_id VARCHAR(64) NULL,
    ADD UNIQUE KEY uq_resources_legacy (legacy_kind, legacy_id);
