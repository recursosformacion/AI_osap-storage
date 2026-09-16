-- ============================================================================
-- Conversión de datos: `osap-storage_v1` (imagen de producción) -> `osap-storage`
-- Re-ejecutable: vacía el destino y vuelve a copiar.
-- Nomenclatura destino: normativa V3 (works_id, languages_id, genres_id...).
-- No ejecuta cambios de esquema.
-- ============================================================================
SET FOREIGN_KEY_CHECKS = 0;
SET NAMES utf8mb4;
SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';

-- ---------------------------------------------------------------------------
-- 0. RESET del destino (solo tablas de datos; se conservan los seeds:
--    epochs, genres, genre_mappings, instruments, instrument_categories,
--    catalog, category, roles, roles_categoria)
-- ---------------------------------------------------------------------------
TRUNCATE TABLE `osap-storage`.works_person_roles;
TRUNCATE TABLE `osap-storage`.works_person_import;
TRUNCATE TABLE `osap-storage`.work_genres;
TRUNCATE TABLE `osap-storage`.work_instruments;
TRUNCATE TABLE `osap-storage`.work_parts;
TRUNCATE TABLE `osap-storage`.work_tag;
TRUNCATE TABLE `osap-storage`.work_language;
TRUNCATE TABLE `osap-storage`.work_statistics;
TRUNCATE TABLE `osap-storage`.works;
TRUNCATE TABLE `osap-storage`.persons_identifiers;
TRUNCATE TABLE `osap-storage`.persons_authority_name;
TRUNCATE TABLE `osap-storage`.persons_authority;
TRUNCATE TABLE `osap-storage`.persons_evidence;
TRUNCATE TABLE `osap-storage`.persons_merge_history;
TRUNCATE TABLE `osap-storage`.persons_aliases;
TRUNCATE TABLE `osap-storage`.persons;
TRUNCATE TABLE `osap-storage`.languages;
TRUNCATE TABLE `osap-storage`.tag_work;
TRUNCATE TABLE `osap-storage`.votes;
TRUNCATE TABLE `osap-storage`.archives;
TRUNCATE TABLE `osap-storage`.archive_entries;
TRUNCATE TABLE `osap-storage`.files;
TRUNCATE TABLE `osap-storage`.storage_locations;
TRUNCATE TABLE `osap-storage`.storage_providers;
TRUNCATE TABLE `osap-storage`.import_sources;
TRUNCATE TABLE `osap-storage`.download_jobs;
TRUNCATE TABLE `osap-storage`.statistics;
TRUNCATE TABLE `osap-storage`.statistics_runs;

-- ---------------------------------------------------------------------------
-- 1. PERSONAS
-- ---------------------------------------------------------------------------
-- 1.1 composers -> persons
INSERT INTO `osap-storage`.persons
 (persons_id, persons_name, persons_visible, persons_birth_year, persons_death_year,
  persons_status, persons_review_status, persons_review_reason, persons_reviewed_at,
  persons_merged_into, persons_merged_at, persons_source_system,
  persons_created_at, persons_updated_at)
SELECT id, name, visible, birth_year, death_year,
       status, review_status, review_reason, reviewed_at,
       merged_into, merged_at, source_system,
       created_at, updated_at
FROM `osap-storage_v1`.composers;

-- 1.2 biographies -> persons.persons_biography_*
UPDATE `osap-storage`.persons p
JOIN `osap-storage_v1`.composer_biographies b ON b.composer_id = p.persons_id
SET p.persons_biography_summary      = b.biography_summary,
    p.persons_biography_era          = b.biography_era,
    p.persons_biography_nationality  = b.biography_nationality,
    p.persons_biography_key_works    = b.biography_key_works,
    p.persons_biography_key_fact     = b.biography_key_fact,
    p.persons_biography_references   = b.biography_references,
    p.persons_biography_updated_at   = b.biography_updated_at;

-- 1.3 aliases: catálogo de idiomas + junction
INSERT INTO `osap-storage`.languages (languages_code)
SELECT DISTINCT a.language
FROM `osap-storage_v1`.composer_aliases a
WHERE a.language IS NOT NULL AND a.language <> '';

INSERT IGNORE INTO `osap-storage`.persons_aliases
 (person_id, person_aliases_alias, person_aliases_normalized_alias,
  person_aliases_name_type, person_aliases_language_id, person_aliases_source, created_at)
SELECT a.composer_id, a.alias, a.normalized_alias,
       a.name_type, l.id, a.source, a.created_at
FROM `osap-storage_v1`.composer_aliases a
LEFT JOIN `osap-storage`.languages l ON l.languages_code = a.language;

-- 1.4 identifiers <- composer_identifiers + musicbrainz_id/cluster_id (de composers)
INSERT INTO `osap-storage`.persons_identifiers
 (persons_id, persons_identifiers_type, persons_identifiers_value, persons_identifiers_source,
  persons_identifiers_is_identity_anchor, persons_identifiers_strength,
  persons_identifiers_channels, persons_identifiers_created_at)
SELECT composer_id, id_type, id_value, source,
       is_identity_anchor, strength, channels, created_at
FROM `osap-storage_v1`.composer_identifiers;

INSERT INTO `osap-storage`.persons_identifiers
 (persons_id, persons_identifiers_type, persons_identifiers_value, persons_identifiers_source,
  persons_identifiers_is_identity_anchor)
SELECT id, 'musicbrainz', musicbrainz_id, 'maestro', 1
FROM `osap-storage_v1`.composers
WHERE musicbrainz_id IS NOT NULL AND musicbrainz_id <> '';

INSERT INTO `osap-storage`.persons_identifiers
 (persons_id, persons_identifiers_type, persons_identifiers_value, persons_identifiers_source,
  persons_identifiers_is_identity_anchor)
SELECT id, 'cluster', cluster_id, 'maestro', 0
FROM `osap-storage_v1`.composers
WHERE cluster_id IS NOT NULL AND cluster_id <> '';

-- 1.5 authority + names (se migra todo; enlace best-effort a persons)
INSERT INTO `osap-storage`.persons_authority
 (authority_id, persons_authority_wikidata_id, persons_authority_viaf_id,
  persons_authority_imslp_id, persons_authority_canonical_name,
  persons_authority_birth_date, persons_authority_death_date)
SELECT authority_id, wikidata_id, viaf_id, imslp_id, canonical_name, birth_date, death_date
FROM `osap-storage_v1`.composer_authority;

UPDATE `osap-storage`.persons_authority pa
JOIN `osap-storage_v1`.composer_authority_names can ON can.authority_id = pa.authority_id
JOIN `osap-storage`.persons p ON p.persons_name = can.name
SET pa.persons_id = p.persons_id;

INSERT INTO `osap-storage`.persons_authority_name
 (authority_id, persons_authority_name_name, persons_authority_name_normalized_name,
  persons_authority_name_source)
SELECT authority_id, name, normalized_name, source
FROM `osap-storage_v1`.composer_authority_names;

-- 1.6 evidence + merge history
INSERT INTO `osap-storage`.persons_evidence
 (id, persons_id, persons_evidence_rule, persons_evidence_decision, persons_evidence_reason,
  persons_evidence_anchor_type, persons_evidence_anchor_value, persons_evidence_channels,
  persons_evidence_identifiers_used, persons_evidence_matcher_version, persons_evidence_created_at)
SELECT id, composer_id, rule, decision, reason, anchor_type, anchor_value,
       channels, identifiers_used, matcher_version, created_at
FROM `osap-storage_v1`.composer_evidence;

INSERT INTO `osap-storage`.persons_merge_history
 (id, merge_operation_id, source_person_id, target_person_id, merged_at, merged_by)
SELECT id, merge_operation_id, source_composer_id, target_composer_id, merged_at, merged_by
FROM `osap-storage_v1`.composer_merge_history;

-- ---------------------------------------------------------------------------
-- 2. WORKS (base)
-- ---------------------------------------------------------------------------
INSERT INTO `osap-storage`.works
 (id, works_song_name, works_title, works_subtitle, works_attr_type, works_attribution_note,
  works_opus, works_catalogue, works_musical_key, works_year, works_duration, works_measures,
  works_pages, works_parts, works_complexity, works_description, works_license,
  works_public_domain, works_relative_path, works_music_digest, works_key,
  works_created_at, works_updated_at)
SELECT id, song_name, title, subtitle, attribution_type, attribution_note,
       opus, catalogue, musical_key, year, duration, measures,
       pages, parts, complexity, description, license,
       public_domain, relative_path, music_digest, work_key,
       created_at, updated_at
FROM `osap-storage_v1`.works;

-- ---------------------------------------------------------------------------
-- 3. ATRIBUCIÓN
-- ---------------------------------------------------------------------------
-- 3.1 composer_id resuelto -> works_person_roles (rol 1 = Composer)
INSERT IGNORE INTO `osap-storage`.works_person_roles
 (works_person_roles_work_id, works_person_roles_person_id, works_person_roles_role_id)
SELECT w.id, w.composer_id, 1
FROM `osap-storage_v1`.works w
JOIN `osap-storage`.persons p ON p.persons_id = w.composer_id
WHERE w.composer_id IS NOT NULL AND w.composer_id <> '';

-- 3.2 staging de textos (resolución de nombres aplazada)
INSERT INTO `osap-storage`.works_person_import
 (works_id, works_person_import_name, works_person_import_role, works_person_import_source)
SELECT id, composer, 'composer', 'pdmx'
FROM `osap-storage_v1`.works
WHERE composer IS NOT NULL AND composer NOT IN ('', 'NA');

INSERT INTO `osap-storage`.works_person_import
 (works_id, works_person_import_name, works_person_import_role, works_person_import_source)
SELECT id, artist, 'artist', 'pdmx'
FROM `osap-storage_v1`.works
WHERE artist IS NOT NULL AND artist NOT IN ('', 'NA');

-- ---------------------------------------------------------------------------
-- 4. JUNCTIONS
-- ---------------------------------------------------------------------------
-- 4.1 work_genres (solo códigos presentes en genre_mappings)
INSERT IGNORE INTO `osap-storage`.work_genres (works_id, genres_id)
SELECT w.id, m.genre_id
FROM `osap-storage_v1`.works w
JOIN `osap-storage_v1`.genre_mappings m ON m.code = w.genre;

-- ---------------------------------------------------------------------------
-- 5. ALMACENAMIENTO (copia literal)
-- ---------------------------------------------------------------------------
INSERT INTO `osap-storage`.storage_providers
 (id, name, provider_type, config, enabled, created_at, updated_at)
SELECT id, name, provider_type, config, enabled, created_at, updated_at
FROM `osap-storage_v1`.storage_providers;

INSERT INTO `osap-storage`.files
 (id, sha256, name, mime_type, size_bytes, status, created_at, updated_at)
SELECT id, sha256, name, mime_type, size_bytes, status, created_at, updated_at
FROM `osap-storage_v1`.files;

INSERT INTO `osap-storage`.archives
 (id, provider_id, name, url, format, local_path, status, size, sha256, downloaded_at,
  created_at, updated_at)
SELECT id, provider_id, name, url, format, local_path, status, size, sha256, downloaded_at,
       created_at, updated_at
FROM `osap-storage_v1`.archives;

INSERT INTO `osap-storage`.storage_locations
 (id, file_id, provider_id, object_key, status, created_at, updated_at)
SELECT id, file_id, provider_id, object_key, status, created_at, updated_at
FROM `osap-storage_v1`.storage_locations;

INSERT INTO `osap-storage`.archive_entries
 (id, archive_id, logical_id, composer, title, work_id, relative_path, file_id, size,
  offset_bytes, status, created_at, updated_at)
SELECT id, archive_id, logical_id, composer, title, work_id, relative_path, file_id, size,
       offset_bytes, status, created_at, updated_at
FROM `osap-storage_v1`.archive_entries;

INSERT INTO `osap-storage`.download_jobs
 (id, file_id, provider_id, source_url, status, error_message, created_at, updated_at)
SELECT id, file_id, provider_id, source_url, status, error_message, created_at, updated_at
FROM `osap-storage_v1`.download_jobs;

INSERT INTO `osap-storage`.import_sources
 (id, provider, version, csv_path, notes, imported_at, created_at, updated_at)
SELECT id, provider, version, csv_path, notes, imported_at, created_at, updated_at
FROM `osap-storage_v1`.import_sources;

INSERT INTO `osap-storage`.statistics
 (id, archives, entries, files, downloaded_tar, materialized, pending, bytes, computed_at,
  created_at, updated_at)
SELECT id, archives, entries, files, downloaded_tar, materialized, pending, bytes, computed_at,
       created_at, updated_at
FROM `osap-storage_v1`.statistics;

INSERT INTO `osap-storage`.statistics_runs
 (id, started_at, finished_at, works_updated, composers_updated)
SELECT id, started_at, finished_at, works_updated, composers_updated
FROM `osap-storage_v1`.statistics_runs;

SET FOREIGN_KEY_CHECKS = 1;
