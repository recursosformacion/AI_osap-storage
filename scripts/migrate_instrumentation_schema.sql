-- ============================================================================
-- Modelo de instrumentación: catálogos (instruments/voices/ensembles),
-- relaciones con la obra (work_instruments/work_voices/work_ensembles) y
-- composición de conjuntos (ensemble_voices).
-- Aditivo. Normativa V3.
-- ============================================================================
SET FOREIGN_KEY_CHECKS = 0;
SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. Catálogo de voces
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `voices` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `voices_name` varchar(80) NOT NULL,
  `voices_sort` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_voices_name` (`voices_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 2. Catálogo de conjuntos (ensembles)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `ensembles` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `ensembles_name` varchar(120) NOT NULL,
  `ensembles_code` varchar(40) NOT NULL,
  `ensembles_description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ensembles_code` (`ensembles_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 3. Composición de un conjunto (qué voces y cuántas)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `ensemble_voices` (
  `ensembles_id` int(10) unsigned NOT NULL,
  `voices_id` int(10) unsigned NOT NULL,
  `ensemble_voices_quantity` int(11) NOT NULL DEFAULT 1,
  `ensemble_voices_order` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`ensembles_id`,`voices_id`),
  KEY `idx_ensemble_voices_voice` (`voices_id`),
  CONSTRAINT `fk_ensemble_voices_ensemble` FOREIGN KEY (`ensembles_id`) REFERENCES `ensembles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ensemble_voices_voice` FOREIGN KEY (`voices_id`) REFERENCES `voices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 4. Relaciones con la obra
-- ---------------------------------------------------------------------------
-- 4.1 work_instruments: se añade cantidad
ALTER TABLE `work_instruments`
  ADD COLUMN IF NOT EXISTS `work_instruments_quantity` int(11) NOT NULL DEFAULT 1 AFTER `instruments_id`;

-- 4.2 work_voices
CREATE TABLE IF NOT EXISTS `work_voices` (
  `works_id` bigint(20) unsigned NOT NULL,
  `voices_id` int(10) unsigned NOT NULL,
  `work_voices_quantity` int(11) NOT NULL DEFAULT 1,
  `work_voices_context` varchar(16) DEFAULT NULL COMMENT 'solo | ensemble',
  PRIMARY KEY (`works_id`,`voices_id`),
  KEY `idx_work_voices_voice` (`voices_id`),
  CONSTRAINT `fk_work_voices_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_work_voices_voice` FOREIGN KEY (`voices_id`) REFERENCES `voices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4.3 work_ensembles
CREATE TABLE IF NOT EXISTS `work_ensembles` (
  `works_id` bigint(20) unsigned NOT NULL,
  `ensembles_id` int(10) unsigned NOT NULL,
  `work_ensembles_quantity` int(11) NOT NULL DEFAULT 1,
  PRIMARY KEY (`works_id`,`ensembles_id`),
  KEY `idx_work_ensembles_ensemble` (`ensembles_id`),
  CONSTRAINT `fk_work_ensembles_work` FOREIGN KEY (`works_id`) REFERENCES `works` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_work_ensembles_ensemble` FOREIGN KEY (`ensembles_id`) REFERENCES `ensembles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 5. Semilla de voces
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO `voices` (id, voices_name, voices_sort) VALUES
 (1,'Soprano',1), (2,'Mezzo-soprano',2), (3,'Contralto',3), (4,'Countertenor',4),
 (5,'Tenor',5), (6,'Baritone',6), (7,'Bass',7), (8,'Treble',8), (9,'Voice',9);

-- ---------------------------------------------------------------------------
-- 6. Semilla de ensembles
-- ---------------------------------------------------------------------------
INSERT IGNORE INTO `ensembles` (id, ensembles_name, ensembles_code, ensembles_description) VALUES
 (1,'SATB Choir','SATB','Coro mixto a 4 voces'),
 (2,"Women's Choir",'SSAA','Coro femenino'),
 (3,"Men's Choir",'TTBB','Coro masculino'),
 (4,"Children's Choir",'CHILD','Coro de niños'),
 (5,'Soprano-Alto-Bass','SAB','Tres voces mixtas'),
 (6,'Soprano-Alto','SA','Dos voces agudas'),
 (7,'Double Choir SATB/SATB','SATB-SATB','Doble coro mixto'),
 (8,'Unison','UNISON','Una sola voz/unísono'),
 (9,'Mixed Choir','MIXED','Coro mixto genérico');

INSERT IGNORE INTO `ensemble_voices` (ensembles_id, voices_id, ensemble_voices_quantity, ensemble_voices_order) VALUES
 (1,1,1,1),(1,3,1,2),(1,5,1,3),(1,7,1,4),          -- SATB
 (2,1,2,1),(2,3,2,2),                               -- SSAA
 (3,5,2,1),(3,7,2,2),                               -- TTBB
 (5,1,1,1),(5,3,1,2),(5,7,1,3),                     -- SAB
 (6,1,1,1),(6,3,1,2),                               -- SA
 (7,1,2,1),(7,3,2,2),(7,5,2,3),(7,7,2,4),           -- SATB/SATB
 (8,9,1,1),                                         -- Unison
 (9,1,1,1),(9,3,1,2),(9,5,1,3),(9,7,1,4);           -- Mixed Choir

-- ---------------------------------------------------------------------------
-- 7. Voces y ensembles salen del catálogo `instruments` (cats 107/108)
-- ---------------------------------------------------------------------------
DELETE FROM `instruments` WHERE `id` IN (71,72,73,74,75,76,77,78,81,82,83,84);

SET FOREIGN_KEY_CHECKS = 1;
