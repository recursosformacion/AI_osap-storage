-- 013 · Rol "Adaptador/a" (id 16, clave API `adapter`).
--
-- El texto de origen del import distingue "arranged by" (arreglista, rol 3) de "adapted by"
-- (adaptador), y el catálogo no tenía rol para lo segundo: las filas adaptador quedaban sin rol
-- y bloqueaban el staging. Se añade el rol con el mismo estilo que el resto ("Compositor/a",
-- "Arreglista", …).
--
-- Idempotente y con guarda: si el id 16 estuviera ocupado por otro rol, el INSERT falla en vez
-- de crear una inconsistencia; y si el rol no queda creado, la migración aborta.

INSERT INTO `roles` (`id`, `role_name`, `role_description`)
SELECT 16, 'Adaptador/a', 'Adaptación de una obra preexistente'
WHERE NOT EXISTS (SELECT 1 FROM `roles` WHERE `id` = 16 OR `role_name` = 'Adaptador/a');

SET @adapter_ok := (
  SELECT COUNT(*) FROM `roles` WHERE `id` = 16 AND `role_name` = 'Adaptador/a'
);
SET @adapter_sql := IF(
  @adapter_ok = 1,
  'DO 0',
  'SELECT * FROM `__migracion_013_abortada__rol_adapter_no_creado`'
);
PREPARE adapter_stmt FROM @adapter_sql;
EXECUTE adapter_stmt;
DEALLOCATE PREPARE adapter_stmt;
