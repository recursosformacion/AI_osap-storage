-- Soporte de obras externas sin fichero local
-- works.relative_path conserva la referencia proporcionada por el proveedor externo
-- (no es una ruta fisica y nunca debe abrirse como fichero)
-- La identidad interna sigue siendo works.id y la deduplicacion usa work_key existente
-- La procedencia del proveedor se conserva en works.tags

ALTER TABLE works
    ADD COLUMN relative_path VARCHAR(1024) NULL AFTER work_key;

CREATE INDEX idx_works_relative_path ON works (relative_path(255));
