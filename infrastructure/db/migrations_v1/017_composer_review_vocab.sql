-- Revisión de compositores: nuevo vocabulario de estado
-- (correct, incorrect, reviewed, not_reviewed)

UPDATE composers SET review_status = 'not_reviewed' WHERE review_status = 'pending';

UPDATE composers SET review_status = 'incorrect' WHERE review_status = 'false';

ALTER TABLE composers MODIFY review_status VARCHAR(16) NOT NULL DEFAULT 'not_reviewed';
