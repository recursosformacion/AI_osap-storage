ALTER TABLE archive_entries
    ADD COLUMN composer VARCHAR(512) NULL AFTER logical_id,
    ADD COLUMN title VARCHAR(512) NULL AFTER composer;
