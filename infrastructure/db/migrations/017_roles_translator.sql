-- 017 · Rol "Traductor/a" (id 17, clave API `translator`).
--
-- El texto de origen del import distingue "translated by" (traducción) y hoy no tenía rol: esas
-- filas quedaban sin rol y la persona se perdía. Se añade con el mismo estilo que el resto.
--
-- Idempotente y con guarda: si el id 17 estuviera ocupado, el INSERT falla; y si el rol no queda
-- creado, la migración aborta.

INSERT INTO `roles` (`id`, `role_name`, `role_description`)
SELECT 17, 'Traductor/a', 'Traducción del texto de una obra'
WHERE NOT EXISTS (SELECT 1 FROM `roles` WHERE `id` = 17 OR `role_name` = 'Traductor/a');

SET @traductor_ok := (
  SELECT COUNT(*) FROM `roles` WHERE `id` = 17 AND `role_name` = 'Traductor/a'
);
SET @traductor_sql := IF(
  @traductor_ok = 1,
  'DO 0',
  'SELECT * FROM `__migracion_017_abortada__rol_traductor_no_creado`'
);
PREPARE traductor_stmt FROM @traductor_sql;
EXECUTE traductor_stmt;
DEALLOCATE PREPARE traductor_stmt;
