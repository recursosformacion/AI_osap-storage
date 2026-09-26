-- 008_merge_voicings_into_ensembles.sql
-- Consolida `voicings`/`work_voicing` en `ensembles`/`work_ensembles`.
--
-- Motivo: el voicing de una obra ES su formación vocal; tener `voicings` era duplicar
-- `ensembles` (349 de 1.408 términos coincidían ya con un `ensembles_code`). Se unifica
-- en el catálogo `ensembles` (+ `ensemble_voices` para la composición en voces).
--
-- Normaliza los códigos a MAYÚSCULAS para evitar duplicados por caja (la unique key es
-- case-insensitive) y amplía `ensembles_code` a 64 (los términos de voicing llegan a 52).

-- 1. Normaliza a mayúsculas los códigos existentes (no puede violar la unique key
--    case-insensitive: dos códigos que colapsen en UPPER ya colisionarían hoy).
UPDATE `ensembles` SET `ensembles_code` = UPPER(`ensembles_code`);

-- 2. Amplía el código para admitir los términos de voicing.
ALTER TABLE `ensembles` MODIFY `ensembles_code` varchar(64) NOT NULL;

-- 3. Promociona los términos de `voicings` al catálogo (dedupe case-insensitive).
INSERT IGNORE INTO `ensembles` (`ensembles_code`, `ensembles_name`)
SELECT DISTINCT UPPER(`voicings_term`), UPPER(`voicings_term`)
FROM `voicings`
WHERE `voicings_term` IS NOT NULL AND `voicings_term` <> '';

-- 4. Lleva la relación obra↔voicing a obra↔ensemble.
INSERT IGNORE INTO `work_ensembles`
    (`works_id`, `ensembles_id`, `work_ensembles_quantity`)
SELECT wv.`works_id`, e.`id`, 1
FROM `work_voicing` wv
JOIN `voicings` v ON v.`id` = wv.`voicings_id`
JOIN `ensembles` e ON e.`ensembles_code` = UPPER(v.`voicings_term`);

-- 5. Retira el modelo duplicado.
DROP TABLE IF EXISTS `work_voicing`;
DROP TABLE IF EXISTS `voicings`;
