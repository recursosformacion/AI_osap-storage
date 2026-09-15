-- Votaciones y estadisticas de obras y compositores (Storage es propietario de los datos)

-- Voto de un usuario sobre una obra. Un usuario solo puede votar una vez al dia por obra
-- (vote_day en UTC). La unicidad se garantiza en la base de datos, no solo en Python

CREATE TABLE IF NOT EXISTS votes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id VARCHAR(255) NOT NULL,
    work_id BIGINT UNSIGNED NOT NULL,
    vote TINYINT NOT NULL,
    voted_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    vote_day DATE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_votes_user_work_day (user_id, work_id, vote_day),
    KEY idx_votes_work (work_id),
    KEY idx_votes_day (vote_day),
    CONSTRAINT fk_votes_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE,
    CONSTRAINT chk_votes_range CHECK (vote BETWEEN 1 AND 5)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- Estadisticas derivadas por obra (solo obras con votos)

CREATE TABLE IF NOT EXISTS work_statistics (
    work_id BIGINT UNSIGNED NOT NULL,
    votes_count INT NOT NULL DEFAULT 0,
    rating_avg DECIMAL(10,2) NULL,
    computed_at DATETIME(6) NULL,
    PRIMARY KEY (work_id),
    CONSTRAINT fk_work_statistics_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- Valoracion agregada por compositor (solo compositores activos). Los merged no reciben
-- estadistica independiente

CREATE TABLE IF NOT EXISTS composer_statistics (
    composer_id CHAR(36) NOT NULL,
    works_count INT NOT NULL DEFAULT 0,
    votes_count INT NOT NULL DEFAULT 0,
    rating_avg DECIMAL(10,2) NULL,
    computed_at DATETIME(6) NULL,
    PRIMARY KEY (composer_id),
    CONSTRAINT fk_composer_statistics_composer FOREIGN KEY (composer_id) REFERENCES composers (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- Registro de ejecuciones del proceso de recalculo

CREATE TABLE IF NOT EXISTS statistics_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    started_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    works_updated INT NOT NULL DEFAULT 0,
    composers_updated INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
