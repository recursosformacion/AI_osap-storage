-- Índice FULLTEXT para la búsqueda RISM local (`rism_sources`, 1,5M filas).
-- Sin él, `search` usaba LIKE '%q%' → full scan (~17s); con MATCH AGAINST baja a ms.
-- Idempotente: si ya existe, MySQL devuelve error 1061 (se puede ignorar).
ALTER TABLE rism_sources
    ADD FULLTEXT INDEX ft_rism_search (rism_uniform_title, rism_title, rism_composer_name);
