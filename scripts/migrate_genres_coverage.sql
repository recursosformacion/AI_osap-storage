-- ============================================================================
-- Cobertura de género: añade códigos base y compuestos y reconstruye work_genres.
-- ============================================================================
SET NAMES utf8mb4;

-- Bases que faltaban en el catálogo
INSERT IGNORE INTO `osap-storage_new`.genre_mappings (code, genre_id) VALUES
('hiphop',6),('metal',5),('country',3),('newage',8),('comedy',12),
('disco',11),('reggaeska',11),('blues',4),('experimental',8),('darkwave',8);

-- Compuestos: se mapean por su primer segmento
INSERT IGNORE INTO `osap-storage_new`.genre_mappings (code, genre_id)
SELECT DISTINCT w.genre, base.genre_id
FROM `osap-storage`.works w
JOIN `osap-storage_new`.genre_mappings base ON base.code = SUBSTRING_INDEX(w.genre, '-', 1)
WHERE w.genre NOT IN ('', 'NA') AND w.genre LIKE '%-%';

-- Reconstrucción de la relación obra <-> género
TRUNCATE TABLE `osap-storage_new`.work_genres;
INSERT IGNORE INTO `osap-storage_new`.work_genres (works_id, genres_id)
SELECT w.id, m.genre_id
FROM `osap-storage`.works w
JOIN `osap-storage_new`.genre_mappings m ON m.code = w.genre
WHERE w.genre NOT IN ('', 'NA');
