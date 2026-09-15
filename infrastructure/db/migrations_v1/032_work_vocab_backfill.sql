-- 032_work_vocab_backfill.sql
-- Siembra work_genres y work_instruments a partir de los textos de works.genre y
-- works.instrumentation (backfill de mantenimiento administrativo; los desplegables
-- del mantenimiento de obra se alimentan de estas tablas).
-- Idempotente: INSERT IGNORE (UNIQUE work_id, genre/instrument).

INSERT IGNORE INTO work_genres (work_id, genre)
SELECT w.id, w.genre
FROM works w
WHERE w.genre IS NOT NULL AND TRIM(w.genre) <> ''
  AND NOT EXISTS (SELECT 1 FROM work_genres g WHERE g.work_id = w.id AND g.genre = w.genre);

INSERT IGNORE INTO work_instruments (work_id, instrument)
SELECT w.id, w.instrumentation
FROM works w
WHERE w.instrumentation IS NOT NULL AND TRIM(w.instrumentation) <> ''
  AND NOT EXISTS (SELECT 1 FROM work_instruments i WHERE i.work_id = w.id AND i.instrument = w.instrumentation);
