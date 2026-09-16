-- ============================================================================
-- Reconversión de junctions restantes: work_parts y work_tags (desde el
-- enriquecimiento de `osap-storage_v1`).
-- ============================================================================
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- Las etiquetas de origen llegan hasta 512 caracteres
ALTER TABLE `tag_work` MODIFY COLUMN `tag_texto` varchar(512) NOT NULL;

TRUNCATE TABLE `osap-storage`.work_parts;
TRUNCATE TABLE `osap-storage`.work_tag;
TRUNCATE TABLE `osap-storage`.tag_work;

-- 1. Partes (deduplicando work_id + part_name)
INSERT INTO `osap-storage`.work_parts (works_id, work_parts_name)
SELECT work_id, part_name
FROM `osap-storage_v1`.work_parts
GROUP BY work_id, part_name;

-- 2. Catálogo de tags
INSERT INTO `osap-storage`.tag_work (tag_texto)
SELECT DISTINCT tag FROM `osap-storage_v1`.work_tags WHERE tag IS NOT NULL AND tag <> '';

-- 3. Relación obra <-> tag
INSERT IGNORE INTO `osap-storage`.work_tag (works_id, tag_id)
SELECT wt.work_id, t.id
FROM `osap-storage_v1`.work_tags wt
JOIN `osap-storage`.tag_work t ON t.tag_texto = wt.tag;

SET FOREIGN_KEY_CHECKS = 1;
