-- 007_voicings.sql
-- Catálogo de voicings + relación N:N con obras. Sustituye `works.works_voicing`
-- (JSON inline) porque una obra puede prepararse para varios sistemas de voces.
--
-- `voicings.voicings_term` guarda el término canónico ya normalizado por
-- `application/services/cpdl_voicing.py` (sin el conteo inicial, p. ej. "EQUAL VOICES").
-- Nace del voicing crudo de CPDL, pero es un catálogo abierto a otros orígenes.
--
-- La columna `works.works_voicing` se retira tras poblar estas tablas
-- (`scripts/backfill_work_voicings.py --drop-source`).

CREATE TABLE IF NOT EXISTS `voicings` (
    `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
    `voicings_term` varchar(64) NOT NULL,
    `voicings_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_voicings_term` (`voicings_term`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `work_voicing` (
    `works_id` bigint(20) unsigned NOT NULL,
    `voicings_id` int(10) unsigned NOT NULL,
    `work_voicing_created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
    PRIMARY KEY (`works_id`,`voicings_id`),
    KEY `idx_work_voicing_voicing` (`voicings_id`),
    CONSTRAINT `fk_work_voicing_voicing` FOREIGN KEY (`voicings_id`)
        REFERENCES `voicings` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_work_voicing_work` FOREIGN KEY (`works_id`)
        REFERENCES `works` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
