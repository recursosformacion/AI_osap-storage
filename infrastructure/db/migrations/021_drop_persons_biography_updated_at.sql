-- 021 · Elimina `persons.persons_biography_updated_at`.
--
-- La biografía ya forma parte del registro `persons`: cualquier edición de sus campos de
-- biografía actualiza también `persons_updated_at`, así que la fecha propia de la biografía
-- era redundante. Se elimina en BD (no se oculta) para no arrastrar dos fechas equivalentes.
--
-- Guardado con information_schema para poder aplicarla aunque la columna ya no exista.

SET @pbiau_cols := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = DATABASE() AND table_name = 'persons'
    AND column_name = 'persons_biography_updated_at'
);
SET @pbiau_sql := IF(
  @pbiau_cols = 1,
  'ALTER TABLE `persons` DROP COLUMN `persons_biography_updated_at`',
  'DO 0'
);
PREPARE pbiau_stmt FROM @pbiau_sql;
EXECUTE pbiau_stmt;
DEALLOCATE PREPARE pbiau_stmt;
