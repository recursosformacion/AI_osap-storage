-- Revisión de compositores: estado de revisión heurística (correct / false / pending).

ALTER TABLE composers
    ADD COLUMN review_status VARCHAR(16) NOT NULL DEFAULT 'pending' AFTER status,
    ADD COLUMN reviewed_at DATETIME(6) NULL AFTER review_status;

CREATE INDEX idx_composers_review_status ON composers (review_status);
