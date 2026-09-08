-- 038_epochs.sql
-- Tabla de épocas históricas de la música para clasificar compositores (era).
-- biography_era (varchar libre) se migrará después a epoch_id (FK) con un mapeo
-- consensuado. Esta tabla queda como catálogo y fuente para el desplegable.

CREATE TABLE IF NOT EXISTS epochs (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(140) NOT NULL,
    year_start INT NULL COMMENT 'año inicio (NULL = sin límite inferior)',
    year_end INT NULL COMMENT 'año fin (NULL = hasta la actualidad)',
    description TEXT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_epoch_title (title)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

INSERT IGNORE INTO epochs (id, title, year_start, year_end, description) VALUES
(1, 'Prehistoria y Música Antigua', NULL, 476,
 'Uso de instrumentos rudimentarios (huesos, piedras) y cantos ligados a rituales religiosos en civilizaciones como Grecia, Roma o Egipto. Destaca el Epitafio de Sícilo.'),
(2, 'Edad Media', 476, 1450,
 'Predomina la música vocal y religiosa, con el canto gregoriano como máximo exponente y el nacimiento de la polifonía.'),
(3, 'Renacimiento', 1450, 1600,
 'Época de equilibrio vocal, gran desarrollo del contrapunto y expansión de la música instrumental. Compositores clave: Josquin des Prez y Palestrina.'),
(4, 'Barroco', 1600, 1750,
 'Nace la ópera y se usa el bajo continuo, con una música llena de dramatismo, contraste y virtuosismo. Representantes principales: Johann Sebastian Bach y Antonio Vivaldi.'),
(5, 'Clasicismo', 1750, 1820,
 'Se impone la claridad, la simetría, la sonata y la gran orquesta sinfónica. Figuras destacadas: Wolfgang Amadeus Mozart y Joseph Haydn.'),
(6, 'Romanticismo', 1820, 1900,
 'La música busca la máxima expresión de la emoción individual, la pasión y el sentimiento nacionalista. Compositores como Beethoven (etapa madura), Chopin y Tchaikovsky.'),
(7, 'Impresionismo y Siglo XX', 1900, NULL,
 'Búsqueda de nuevas armonías, ruptura de la tonalidad tradicional, música experimental y la llegada de la electrónica.');
