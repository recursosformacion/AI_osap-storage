-- 041_instrument_catalog.sql
-- Catálogo jerárquico de instrumentos (MusicBrainz) + códigos IMSLP y voces.
-- Tablas nuevas:
--   instrument_categories : categoría raíz y subfamilia (dos niveles, parent_id)
--   instruments           : instrumento/voz/conjunto (code MB, name_en/es, aliases,
--                           imslp_codes, clef, voicing_parts)
--   genre_mappings        : código genre MB (work_genres) -> macro-familia (genres)
--   works_instruments     : asignación obra -> instrumento (vacía; se rellenará
--                           cuando las obras declaren instrumentación)

CREATE TABLE IF NOT EXISTS instrument_categories (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(120) NOT NULL,
    mb_type VARCHAR(40) NOT NULL DEFAULT '',
    parent_id INT UNSIGNED NULL,
    sort INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_inst_cat_code (code),
    CONSTRAINT fk_inst_cat_parent FOREIGN KEY (parent_id)
        REFERENCES instrument_categories (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS instruments (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(60) NOT NULL,
    category_id INT UNSIGNED NOT NULL,
    name_en VARCHAR(120) NOT NULL,
    name_es VARCHAR(120) NOT NULL,
    aliases JSON NULL,
    imslp_codes JSON NULL,
    clef VARCHAR(16) NULL,
    voicing_parts JSON NULL,
    sort INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uq_instrument_code (code),
    CONSTRAINT fk_instrument_cat FOREIGN KEY (category_id)
        REFERENCES instrument_categories (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS genre_mappings (
    code VARCHAR(60) NOT NULL,
    genre_id INT UNSIGNED NOT NULL,
    PRIMARY KEY (code),
    CONSTRAINT fk_genre_mapping_genre FOREIGN KEY (genre_id) REFERENCES genres (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS works_instruments (
    work_id BIGINT UNSIGNED NOT NULL,
    instrument_id INT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (work_id, instrument_id),
    CONSTRAINT fk_works_inst_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE,
    CONSTRAINT fk_works_inst_instrument FOREIGN KEY (instrument_id) REFERENCES instruments (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- Categorías (raíz y subfamilia)
INSERT IGNORE INTO instrument_categories (id, code, name, mb_type, parent_id, sort) VALUES
(1,'wind','Wind (Viento)','wind',NULL,1),
(2,'stringed','Stringed (Cuerda)','string',NULL,2),
(3,'percussion','Percussion (Percusión)','percussion',NULL,3),
(4,'keyboard','Keyboard (Teclado)','keyboard',NULL,4),
(5,'voice','Voice (Voz)','vocal',NULL,5),
(6,'electronic','Electronic / Other','electronic',NULL,6),
(101,'woodwind','Woodwind (Viento Madera)','woodwind',1,1),
(102,'brass','Brass (Viento Metal)','brass',1,2),
(103,'bowed_string','Bowed String (Cuerda Frotada)','string',2,1),
(104,'plucked_string','Plucked String (Cuerda Pulsada)','string',2,2),
(105,'pitched_percussion','Pitched Percussion (Percusión Afinada)','percussion',3,1),
(106,'unpitched_percussion','Unpitched Percussion (Percusión Indeterminada)','percussion',3,2),
(107,'solo_voice','Solo Voice (Solo Vocal)','vocal',5,1),
(108,'vocal_ensemble','Vocal Ensemble (Conjunto Coral)','vocal',5,2);

-- Instrumentos y voces. name_es = alias español principal del JSON; imslp_codes = códigos IMSLP.
INSERT IGNORE INTO instruments (id, code, category_id, name_en, name_es, aliases, imslp_codes, clef, sort) VALUES
(1,'flute',101,'Flute','Flauta','["Flauta travesera"]','["fl"]',NULL,1),
(2,'piccolo',101,'Piccolo','Flautín','["Piccolo"]','["picc"]',NULL,2),
(3,'recorder',101,'Recorder','Flauta dulce','["Recorder"]',NULL,NULL,3),
(4,'oboe',101,'Oboe','Oboe','[]','["ob"]',NULL,4),
(5,'english_horn',101,'English Horn','Corno inglés','["English Horn"]','["eh"]',NULL,5),
(6,'clarinet',101,'Clarinet','Clarinete','[]','["cl"]',NULL,6),
(7,'bass_clarinet',101,'Bass Clarinet','Clarinete bajo','[]','["bcl"]',NULL,7),
(8,'bassoon',101,'Bassoon','Fagot','[]','["bn","bsn"]',NULL,8),
(9,'contrabassoon',101,'Contrabassoon','Contrafagot','[]','["cbn"]',NULL,9),
(10,'saxophone',101,'Saxophone','Saxofón','["Saxo"]',NULL,NULL,10),
(11,'french_horn',102,'French Horn','Trompa','["Horn","Corno francés"]','["hn"]',NULL,1),
(12,'trumpet',102,'Trumpet','Trompeta','[]','["tpt"]',NULL,2),
(13,'cornet',102,'Cornet','Corneta','[]',NULL,NULL,3),
(14,'flugelhorn',102,'Flugelhorn','Fiscornio','[]',NULL,NULL,4),
(15,'trombone',102,'Trombone','Trombón','[]','["tbn"]',NULL,5),
(16,'bass_trombone',102,'Bass Trombone','Trombón bajo','[]',NULL,NULL,6),
(17,'euphonium',102,'Euphonium','Bombardino','[]',NULL,NULL,7),
(18,'tuba',102,'Tuba','Tuba','[]','["tba"]',NULL,8),
(21,'violin',103,'Violin','Violín','[]','["vln"]',NULL,1),
(22,'viola',103,'Viola','Viola','[]','["vla"]',NULL,2),
(23,'cello',103,'Cello','Violonchelo','["Cello"]','["vc"]',NULL,3),
(24,'double_bass',103,'Double Bass','Contrabajo','[]','["db"]',NULL,4),
(25,'viola_da_gamba',103,'Viola da Gamba','Viola de gamba','[]',NULL,NULL,5),
(31,'acoustic_guitar',104,'Acoustic Guitar','Guitarra acústica','["Guitarra clásica"]',NULL,NULL,1),
(32,'electric_guitar',104,'Electric Guitar','Guitarra eléctrica','[]',NULL,NULL,2),
(33,'bass_guitar',104,'Bass Guitar','Bajo eléctrico','[]',NULL,NULL,3),
(34,'harp',104,'Harp','Arpa','[]','["hp"]',NULL,4),
(35,'lute',104,'Lute','Laúd','[]',NULL,NULL,5),
(36,'theorbo',104,'Theorbo','Tiorba','[]',NULL,NULL,6),
(37,'mandolin',104,'Mandolin','Mandolina','[]',NULL,NULL,7),
(38,'banjo',104,'Banjo','Banjo','[]',NULL,NULL,8),
(39,'ukulele',104,'Ukulele','Ukelele','[]',NULL,NULL,9),
(40,'vihuela',104,'Vihuela','Vihuela','[]',NULL,NULL,10),
(41,'timpani',105,'Timpani','Timbales orquestales','[]','["timp"]',NULL,1),
(42,'xylophone',105,'Xylophone','Xilófono','[]',NULL,NULL,2),
(43,'marimba',105,'Marimba','Marimba','[]',NULL,NULL,3),
(44,'vibraphone',105,'Vibraphone','Vibráfono','[]',NULL,NULL,4),
(45,'glockenspiel',105,'Glockenspiel','Lira','["Campanólogo"]',NULL,NULL,5),
(46,'tubular_bells',105,'Tubular Bells','Campanas tubulares','[]',NULL,NULL,6),
(51,'snare_drum',106,'Snare Drum','Caja','["Redoblante"]',NULL,NULL,1),
(52,'bass_drum',106,'Bass Drum','Bombo','[]',NULL,NULL,2),
(53,'cymbals',106,'Cymbals','Platos','["Platillos"]',NULL,NULL,3),
(54,'triangle',106,'Triangle','Triángulo','[]',NULL,NULL,4),
(55,'tambourine',106,'Tambourine','Pandereta','[]',NULL,NULL,5),
(56,'tam_tam',106,'Tam-tam','Tam-tam','["Gong"]',NULL,NULL,6),
(57,'castanets',106,'Castanets','Castañuelas','[]',NULL,NULL,7),
(61,'piano',4,'Piano','Piano','[]','["pno"]',NULL,1),
(62,'pipe_organ',4,'Pipe Organ','Órgano','["Órgano de tubos"]','["org"]',NULL,2),
(63,'harpsichord',4,'Harpsichord','Clave','["Clavecín","Cémbalo"]','["hpd"]',NULL,3),
(64,'clavichord',4,'Clavichord','Clavicordio','[]',NULL,NULL,4),
(65,'celesta',4,'Celesta','Celesta','[]',NULL,NULL,5),
(66,'accordion',4,'Accordion','Acordeón','[]',NULL,NULL,6),
(67,'harmonium',4,'Harmonium','Armonio','[]',NULL,NULL,7),
(71,'soprano',107,'Soprano','Soprano','[]',NULL,'treble',1),
(72,'mezzo_soprano',107,'Mezzo-soprano','Mezzosoprano','[]',NULL,'treble',2),
(73,'alto',107,'Contralto','Contralto','["Alto"]',NULL,'treble',3),
(74,'countertenor',107,'Countertenor','Contratenor','[]',NULL,'treble',4),
(75,'tenor',107,'Tenor','Tenor','[]',NULL,'treble_8vb',5),
(76,'baritone',107,'Baritone','Barítono','[]',NULL,'bass',6),
(77,'bass_voice',107,'Bass','Bajo','[]',NULL,'bass',7),
(78,'treble',107,'Treble','Voz blanca','["Soprano infantil"]',NULL,'treble',8),
(81,'satb_choir',108,'SATB Choir','Coro mixto','["Coro SATB"]',NULL,NULL,1),
(82,'womens_choir',108,"Women's Choir (SSAA)","Coro femenino",'["Voces blancas"]',NULL,NULL,2),
(83,'mens_choir',108,"Men's Choir (TTBB)","Coro masculino",'["Coro grave"]',NULL,NULL,3),
(84,'childrens_choir',108,"Children's Choir","Coro de niños",'["Pueri Cantores"]',NULL,NULL,4),
(91,'synthesizer',6,'Synthesizer','Sintetizador','[]',NULL,NULL,1),
(92,'electric_piano',6,'Electric Piano','Piano eléctrico','["Rhodes"]',NULL,NULL,2),
(93,'theremin',6,'Theremin','Theremín','[]',NULL,NULL,3),
(94,'sampler',6,'Sampler','Muestreador','[]',NULL,NULL,4),
(95,'tape',6,'Tape','Cinta magnética','["Electrónica fija"]',NULL,NULL,5);

-- Mapeo de códigos de género (work_genres / works.genre) a macro-familias (genres)
INSERT IGNORE INTO genre_mappings (code, genre_id) VALUES
('classical',1),('classical-soundtrack',1),('jazz-classical',1),
('religiousmusic',2),
('folk',3),('worldmusic',3),
('jazz',4),
('rock',5),('rock-pop',5),
('pop',6),('rockpop',6),
('electronic',8),
('pop-rbfunksoul',11),('rbfunksoul',11),('rbfunk-soul',11),
('soundtrack',12);
