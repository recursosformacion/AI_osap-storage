ALTER TABLE works
    MODIFY subtitle TEXT NULL,
    MODIFY instrumentation TEXT NULL;

ALTER TABLE work_tags MODIFY tag VARCHAR(512) NOT NULL;
ALTER TABLE work_instruments MODIFY instrument VARCHAR(512) NOT NULL;
ALTER TABLE work_parts MODIFY part_name VARCHAR(512) NOT NULL;
