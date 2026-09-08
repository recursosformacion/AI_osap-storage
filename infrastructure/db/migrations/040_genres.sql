-- 040_genres.sql
-- Catálogo de géneros de obras (macro-familia) con su ámbito y especificidad técnica.
-- Nota: `work_genres` ya existe como tabla de ASIGNACIÓN obra -> genre (work_id, genre);
-- por eso el catálogo se llama `genres`. Igual que `epochs`: fuente para el desplegable
-- de género en el mantenimiento de obras y para futuros filtros. El texto libre de
-- `works.genre` se mapeará después a estos ids de forma consensuada.

CREATE TABLE IF NOT EXISTS genres (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(140) NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_genre_name (name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

INSERT IGNORE INTO genres (id, name, description) VALUES
(1, 'Música Clásica / Docta',
 'Desde la polifonía medieval y la música renacentista hasta el barroco, clasicismo, romanticismo y las vanguardias atonales/contemporáneas.'),
(2, 'Música Sacra / Himnología',
 'Tradiciones litúrgicas, cantos gregorianos, himnos protestantes, cantatas, música de catedral y espirituales negros.'),
(3, 'Tradición Folclórica y Etnomusicología',
 'Músicas de tradición oral regionales (música andina, flamenca, balcánica, celta, gamelán, etc.).'),
(4, 'Jazz y Blues',
 'Ragtime, dixieland, swing, bebop, cool jazz, modal, free jazz y blues rural/urbano.'),
(5, 'Rock y Metal',
 'Desde el rockabilly y rock psicodélico hasta el hard rock, punk, prog rock y las variantes del heavy metal.'),
(6, 'Pop',
 'Estructuras estróficas comerciales, synthpop, teen pop, electropop e indie pop.'),
(7, 'Música Urbana y Hip Hop',
 'Boom bap, trap, drill, R&B contemporáneo, reguetón y dancehall.'),
(8, 'Música Electrónica y Dance',
 'Techno, house, trance, drum & bass, ambient, IDM y EDM.'),
(9, 'Música Latina y Caribeña',
 'Salsa, cumbia, merengue, bachata, son cubano, bossa nova y tango.'),
(10, 'Country, Folk y Americana',
 'Bluegrass, country tradicional, honky-tonk y neofolk.'),
(11, 'Soul, Funk y Disco',
 'Motown, R&B clásico, funk psicodélico, disco y neo-soul.'),
(12, 'Música Escénica y Aplicada',
 'Bandas sonoras de cine (film scores), videojuegos, teatro musical, ópera y zarzuela.');
