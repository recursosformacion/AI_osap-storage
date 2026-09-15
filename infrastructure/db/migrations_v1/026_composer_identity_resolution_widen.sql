-- 026_composer_identity_resolution_widen.sql
-- El nombre de compositor en works.composer es VARCHAR(1024) y attribution (255) desbordaba
-- y abortaba la pasada con DataError 1406. Se amplia attribution y decision_reason a 1024.

ALTER TABLE composer_identity_resolution
    MODIFY COLUMN attribution VARCHAR(1024) NULL,
    MODIFY COLUMN decision_reason VARCHAR(1024) NULL;
