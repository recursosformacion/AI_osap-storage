-- v1 final: suavizado bayesiano hacia la media global, confidence y pesos sqrt.
-- Los campos congelados de estadísticas: rating, adjusted_rating, vote_count,
-- work_count, confidence, calculated_at.

ALTER TABLE work_statistics
    CHANGE COLUMN votes_count vote_count INT NOT NULL DEFAULT 0,
    CHANGE COLUMN rating_avg rating DECIMAL(10,3) NULL,
    CHANGE COLUMN computed_at calculated_at DATETIME(6) NULL,
    ADD COLUMN adjusted_rating DECIMAL(10,3) NULL AFTER rating,
    ADD COLUMN work_count INT NOT NULL DEFAULT 1 AFTER vote_count,
    ADD COLUMN confidence DECIMAL(5,4) NULL AFTER work_count;

ALTER TABLE composer_statistics
    CHANGE COLUMN works_count work_count INT NOT NULL DEFAULT 0,
    CHANGE COLUMN votes_count vote_count INT NOT NULL DEFAULT 0,
    CHANGE COLUMN rating_avg rating DECIMAL(10,3) NULL,
    CHANGE COLUMN computed_at calculated_at DATETIME(6) NULL,
    ADD COLUMN adjusted_rating DECIMAL(10,3) NULL AFTER rating,
    ADD COLUMN confidence DECIMAL(5,4) NULL AFTER work_count;
