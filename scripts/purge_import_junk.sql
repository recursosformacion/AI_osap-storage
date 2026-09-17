-- Limpieza de `works_person_import`: cierra como IGNORADO (resolved = 2) lo que no es una
-- persona y como ASIGNADO (resolved = 1) los anónimos, que ya tienen su marca en `works`.
--
-- Criterios de "basura" (no es un nombre de persona):
--   - placeholders de recopilación: `Misc …`, various, unknown, untitled, etc.
--   - nombres de 2-3 letras (iniciales sueltas).
--   - usuarios/ids: contienen dígitos, o una sola palabra de ≤12 caracteres, o de >12
--     (usuarios de MuseScore tipo `user733509807`, `TimboneTopher`).
--   - urls / dominios / correos.
--   - frases larguísimas (>40) y títulos de obra (`… tune.`).
--   - agrupaciones y sellos: Band, Games, Orchestra, Choir, Ensemble, Records, Music…
--   - anónimos/tradicionales -> ASIGNADOS (resolved = 1).

-- 1) Anónimos y tradicionales: asignados.
UPDATE `works_person_import` SET `works_person_import_resolved` = 1
WHERE `works_person_import_resolved` = 0
AND LOWER(`works_person_import_name`)
    REGEXP '^(various|unknown|anonymous|anon\\.?|trad\\.?|traditional|desconocido|unattributed)';

-- 2) Basura: ignorados.
UPDATE `works_person_import` SET `works_person_import_resolved` = 2
WHERE `works_person_import_resolved` = 0
AND (
     `works_person_import_name` LIKE 'Misc%'
  OR LOWER(`works_person_import_name`)
     REGEXP '^(unattributed|untitled|test|track|album|recording|playback)'
  OR CHAR_LENGTH(TRIM(`works_person_import_name`)) <= 3
  OR `works_person_import_name` REGEXP '[0-9]'
  OR `works_person_import_name` REGEXP 'http|www|@|\\.(com|org|net)'
  OR CHAR_LENGTH(`works_person_import_name`) > 40
  OR (`works_person_import_name` NOT LIKE '% %' AND CHAR_LENGTH(TRIM(`works_person_import_name`)) <= 12)
  OR (`works_person_import_name` NOT LIKE '% %' AND CHAR_LENGTH(TRIM(`works_person_import_name`)) > 12)
  OR `works_person_import_name`
     REGEXP '[[:<:]](Band|Games|Orchestra|Choir|Ensemble|Records|Music|Tune|Tunes|Trio|Quartet|Company|Ltd)[[:>:]]'
  OR `works_person_import_name` LIKE '%tune.%'
);
