-- 005: unificar COLLATION a utf8mb4_unicode_ci en las tablas de texto que quedaron en
-- utf8mb4_general_ci (causa de errores 1267 en JOINs, p. ej. works ⨝ persons).
--
-- NO se tocan las columnas `utf8mb4_bin` (JSON/valores técnicos): su comparación es
-- case-sensitive a propósito y no participan en JOINs por nombre.
--
-- `works` (310k filas) se reconstruye: puede tardar; ejecutar en ventana de mantenimiento.
ALTER TABLE `catalog`  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `category` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `roles`    CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE `works`    CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- `CONVERT TO` cambia TODAS las columnas de la tabla; se restauran las dos que deben seguir
-- siendo case-sensitive (`utf8mb4_bin`) porque guardan JSON/valores técnicos.
ALTER TABLE `works`
    MODIFY `works_voicing` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
    MODIFY `works_instrumentation` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL;
