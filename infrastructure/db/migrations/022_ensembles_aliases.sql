-- 022: alias de códigos de `ensembles` -> fila canónica.
-- Conserva cada `ensembles_code` original que no es su id canónico, apuntando a la fila
-- canónica (`ensembles_code = id_canonico`). Ver docs/osap/ensemble-canonical-model.md.
CREATE TABLE IF NOT EXISTS `ensembles_aliases` (
  `raw_code`     VARCHAR(128)     NOT NULL,
  `ensembles_id` INT(10) UNSIGNED NOT NULL,
  `created_at`   DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`raw_code`),
  KEY `idx_ensembles_aliases_ensemble` (`ensembles_id`),
  CONSTRAINT `fk_ensembles_aliases_ensemble` FOREIGN KEY (`ensembles_id`)
    REFERENCES `ensembles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
