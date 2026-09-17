-- Purga de basura en `persons_identity` (solo CANDIDATOS: persons_id IS NULL).
--
-- Elimina entradas que no son personas:
--   - obras: palabras de género musical (con límites de palabra, para no cargarse
--     "Domenico Della-Maria" por "aria" dentro de "Maria");
--   - catálogos de obra (Op., BWV, Hob., WoO, HWV...);
--   - QIDs de Wikidata usados como nombre (^Q12345$);
--   - nombres con dígitos y nombres absurdamente largos (>60).
--
-- NUNCA toca filas con persons_id (personas nuestras) ni las filas canónicas.
-- Backup previo: `persons_identity_bak`.

DELETE FROM `persons_identity`
WHERE `persons_id` IS NULL AND (
  `identity_name` REGEXP '[[:<:]](Symphony|Sonata|Sonatina|Quartet|Quintet|Trio|Concerto|Prelude|Fugue|Mass|Requiem|Suite|Etude|Nocturne|Waltz|March|Motet|Cantata|Aria|Duo|Sextet|Bagatelle|Rondo|Variation|Lied|Song|Hymn|Choral|Opera|Ballet|Overture|Serenade|Impromptu|Offertory|Anthem|Misc|Various|Unknown|Anonymous|Traditional|Unattributed|Untitled|Track|Album|Recording)[[:>:]]'
  OR `identity_name` REGEXP '[[:<:]](Op\\.|BWV|Hob\\.|WoO|HWV|BuxWV|SWV|TWV|KV)[[:>:]]'
  OR `identity_name` REGEXP '^Q[0-9]+$'
  OR `identity_name` REGEXP '[0-9]'
  OR CHAR_LENGTH(`identity_name`) > 60
);
