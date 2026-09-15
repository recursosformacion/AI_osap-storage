-- ============================================================================
-- Ampliación del catálogo `instruments` con lo no mapeado del enriquecimiento
-- + columna `works_instruments`... no: `works.works_instrumentation` para CPDL.
-- ============================================================================
SET NAMES utf8mb4;

ALTER TABLE `works`
  ADD COLUMN IF NOT EXISTS `works_instrumentation` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL;

INSERT IGNORE INTO `instruments` (code, name_en, name_es, category_id) VALUES
-- percusión indeterminada (106)
('hand_clap','Hand clap','Palmadas',106),
('woodblock','Woodblock','Caja china',106),
('claves','Claves','Claves',106),
('tom_tom','Tom tom','Tom',106),
('maraca','Maraca','Maracas',106),
('conga','Conga','Conga',106),
('bongo','Bongo','Bongó',106),
('hi_hat','Hi-hat','Charles',106),
('cabasa','Cabasa','Cabasa',106),
('guiro','Guiro','Güiro',106),
('temple_block','Temple block','Bloque de templo',106),
('frame_drum','Frame drum','Pandero',106),
('rototom','Rototom','Rototom',106),
('timbale','Timbale','Timbal',106),
('sand_block','Sand block','Bloque de arena',106),
('brake_drums','Brake drums','Tambor de freno',106),
('ratchet','Ratchet','Carraca',106),
('vibraslap','Vibraslap','Vibraslap',106),
('splash_cymbal','Splash','Splash',106),
('ride_cymbal','Ride','Ride',106),
-- percusión afinada (105)
('percussion_bells','Percussion bells','Campanas',105),
('crotales','Crotales','Crotales',105),
('metallophone','Metallophone','Metalófono',105),
('kalimba','Kalimba','Kalimba',105),
('handbells','Handbells','Campanillas',105),
('steel_drums','Steel drums','Tambores de acero',105),
('tabla','Tabla','Tabla',105),
-- viento madera (101)
('saxophone_bass','Saxophone bass','Saxofón bajo',101),
('flute_bass','Flute bass','Flauta bajo',101),
('flute_contra_alto','Flute contra-alto','Flauta contraalto',101),
('pipes','Pipes','Gaitas',101),
-- viento metal (102)
('trumpet_in_d','Trumpet in d','Trompeta en re',102),
('trumpet_piccolo','Trumpet piccolo','Trompeta piccolo',102),
('trumpet_bass','Trumpet bass','Trompeta baja',102),
('trumpet_tenor','Trumpet tenor','Trompeta tenor',102),
('alto_horn','Alto horn','Trompa alto',102),
('vienna_horn','Vienna horn','Trompa vienesa',102),
('kuhlohorn','Kuhlohorn','Kuhlohorn',102),
-- cuerda frotada (103)
('viol','Viol','Viola antigua',103),
('nyckelharpa','Nyckelharpa','Nyckelharpa',103),
('erhu','Erhu','Erhu',103),
('baryton','Baryton','Baritón',103),
-- cuerda pulsada (104)
('tambura','Tambura','Tambura',104),
('sitar','Sitar','Sitar',104),
('shamisen','Shamisen','Shamisen',104),
('bouzouki','Bouzouki','Bouzouki',104),
('balalaika','Balalaika','Balalaica',104),
('balalaika_alto','Balalaika alto','Balalaica alto',104),
('balalaika_bass','Balalaika bass','Balalaica bajo',104),
('balalaika_contrabass','Balalaika contrabass','Balalaica contrabajo',104),
('balalaika_prima','Balalaika prima','Balalaica prima',104),
('balalaika_piccolo','Balalaika piccolo','Balalaica piccolo',104),
-- teclado (4)
('virginal','Virginal','Virginal',4),
-- electrónico / otros (6)
('harmonica','Harmonica','Armónica',6),
('melodica','Melodica','Melódica',6),
('kazoo','Kazoo','Kazoo',6),
('concertina','Concertina','Concertina',6),
('bandoneon','Bandoneon','Bandoneón',6),
('ondes_martenot','Ondes martenot','Ondas Martenot',6),
('effect','Effect','Efecto',6),
('stamp','Stamp','Pisada',6),
('snap','Snap','Chasquido',6),
('chinese','Chinese','Chino',6),
-- grupos/secciones (familia según el nombre)
('drum_group','Drum group','Grupo de percusión',106),
('drum_other','Drum (other)','Percusión (otros)',106),
('percussion_pitched_other','Percussion - pitched (other)','Percusión afinada (otros)',105),
('percussion_metal_other','Percussion - metal (other)','Percusión metal (otros)',106),
('percussion_wood_other','Percussion - wood (other)','Percusión madera (otros)',106),
('strings_group','Strings group','Grupo de cuerda',103),
('strings_plucked_other','Strings - plucked (other)','Cuerda pulsada (otros)',104),
('strings_bowed_other','Strings - bowed (other)','Cuerda frotada (otros)',103),
('woodwinds_group','Woodwinds group','Grupo de viento madera',101),
('woodwinds_other','Woodwinds (other)','Viento madera (otros)',101),
('brass_group','Brass group','Grupo de viento metal',102),
('brass_other','Brass (other)','Viento metal (otros)',102);
