-- Fusión de identidad: `persons_authority` + `persons_authority_name` + `persons_identifiers`
-- -> una sola tabla `persons_identity`.
--
-- Modelo:
--   - `persons_identity` es EAV de identificadores + nombres, con `persons_id` opcional:
--     `persons_id IS NULL` = candidato (aún no es persona nuestra).
--     Fila canónica por persona/ candidato: identity_is_anchor = 1, identity_type = ''.
--   - Nombres: `persons.persons_name` (canónico) + `persons_aliases` (variantes del catálogo).
--   - Se eliminan `persons_authority`, `persons_authority_name` y `persons_identifiers`
--     (backups en `*_bak`).
--
-- Re-ejecutable: se puede relanzar desde los backups.

SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `persons_identity` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `persons_id` char(36) DEFAULT NULL,
  `identity_name` varchar(255) NOT NULL,
  `identity_name_norm` varchar(128) NOT NULL DEFAULT '',
  `identity_type` varchar(24) NOT NULL DEFAULT '' COMMENT 'wikidata_qid|viaf|imslp|isni|... (vacío = solo nombre)',
  `identity_value` varchar(255) NOT NULL DEFAULT '',
  `identity_source` varchar(32) NOT NULL DEFAULT '' COMMENT 'authority|wikidata|maestro|cpdl|web',
  `identity_is_anchor` tinyint(1) NOT NULL DEFAULT 0,
  `identity_strength` varchar(16) DEFAULT NULL,
  `identity_channels` longtext DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_identity_person` (`persons_id`),
  KEY `idx_identity_name_norm` (`identity_name_norm`),
  KEY `idx_identity_type_value` (`identity_type`,`identity_value`),
  CONSTRAINT `fk_persons_identity_person` FOREIGN KEY (`persons_id`) REFERENCES `persons` (`persons_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

TRUNCATE TABLE `persons_identity`;

-- 1) Identificadores ya existentes por persona (EAV previo).
INSERT INTO `persons_identity`
 (persons_id, identity_name, identity_name_norm, identity_type, identity_value,
  identity_source, identity_is_anchor, identity_strength, identity_channels)
SELECT i.persons_id, COALESCE(p.persons_name, ''), '', i.persons_identifiers_type,
       i.persons_identifiers_value, i.persons_identifiers_source,
       i.persons_identifiers_is_identity_anchor, i.persons_identifiers_strength,
       i.persons_identifiers_channels
FROM `persons_identifiers` i LEFT JOIN `persons` p ON p.persons_id = i.persons_id;

-- 2) Autoridad: fila canónica por autoridad (nombre + ancla).
INSERT INTO `persons_identity`
 (persons_id, identity_name, identity_name_norm, identity_type, identity_value,
  identity_source, identity_is_anchor)
SELECT a.persons_id, a.persons_authority_canonical_name,
       COALESCE((SELECT n.persons_authority_name_normalized_name
                 FROM `persons_authority_name` n WHERE n.authority_id = a.authority_id LIMIT 1), ''),
       '', '', 'authority', 1
FROM `persons_authority` a;

-- 3) Autoridad: identificadores (una fila por tipo con valor).
INSERT INTO `persons_identity`
 (persons_id, identity_name, identity_name_norm, identity_type, identity_value,
  identity_source, identity_is_anchor)
SELECT a.persons_id, a.persons_authority_canonical_name, '', 'wikidata_qid',
       a.persons_authority_wikidata_id, 'authority', 0
FROM `persons_authority` a
WHERE a.persons_authority_wikidata_id IS NOT NULL AND a.persons_authority_wikidata_id <> ''
UNION ALL
SELECT a.persons_id, a.persons_authority_canonical_name, '', 'viaf',
       a.persons_authority_viaf_id, 'authority', 0
FROM `persons_authority` a
WHERE a.persons_authority_viaf_id IS NOT NULL AND a.persons_authority_viaf_id <> ''
UNION ALL
SELECT a.persons_id, a.persons_authority_canonical_name, '', 'imslp',
       a.persons_authority_imslp_id, 'authority', 0
FROM `persons_authority` a
WHERE a.persons_authority_imslp_id IS NOT NULL AND a.persons_authority_imslp_id <> '';

-- 4) Autoridad: nombres variantes (no canónicos) como filas de nombre.
INSERT INTO `persons_identity`
 (persons_id, identity_name, identity_name_norm, identity_type, identity_value,
  identity_source, identity_is_anchor)
SELECT a.persons_id, n.persons_authority_name_name, n.persons_authority_name_normalized_name,
       '', '', 'authority', 0
FROM `persons_authority_name` n
JOIN `persons_authority` a ON a.authority_id = n.authority_id
WHERE n.persons_authority_name_name <> a.persons_authority_canonical_name;

-- 5) Los nombres de autoridad con persona pasan al catálogo de alias de la persona.
INSERT IGNORE INTO `persons_aliases`
 (person_id, person_aliases_alias, person_aliases_normalized_alias,
  person_aliases_name_type, person_aliases_source)
SELECT a.persons_id, n.persons_authority_name_name, n.persons_authority_name_normalized_name,
       'authority', 'authority'
FROM `persons_authority_name` n
JOIN `persons_authority` a ON a.authority_id = n.authority_id
WHERE a.persons_id IS NOT NULL;

-- 6) Fila canónica para toda persona que aún no tenga una (invariante: 1 por persona).
INSERT INTO `persons_identity`
 (persons_id, identity_name, identity_name_norm, identity_type, identity_value,
  identity_source, identity_is_anchor)
SELECT p.persons_id, p.persons_name, '', '', '',
       COALESCE(p.persons_source_system, ''), 1
FROM `persons` p
WHERE NOT EXISTS (SELECT 1 FROM `persons_identity` x
                  WHERE x.persons_id = p.persons_id AND x.identity_is_anchor = 1);

DROP TABLE IF EXISTS `persons_authority_name`;
DROP TABLE IF EXISTS `persons_authority`;
DROP TABLE IF EXISTS `persons_identifiers`;

SET FOREIGN_KEY_CHECKS = 1;
