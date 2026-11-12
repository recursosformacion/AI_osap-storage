-- V6 — Resource de referencia explícito de una Work.
ALTER TABLE works
    ADD COLUMN reference_resource_id BIGINT UNSIGNED NULL,
    ADD KEY idx_works_reference_resource (reference_resource_id),
    ADD CONSTRAINT fk_works_reference_resource FOREIGN KEY (reference_resource_id)
        REFERENCES resources (id) ON DELETE SET NULL;
