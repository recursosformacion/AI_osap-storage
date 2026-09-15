-- ============================================================================
-- Ampliación adicional (CPDL): instrumentos/grupos y ensembles con estilo
-- ============================================================================
SET NAMES utf8mb4;

INSERT IGNORE INTO `instruments` (code, name_en, name_es, category_id) VALUES
('basso_continuo','Basso continuo','Bajo continuo',6),
('keyboard','Keyboard','Teclado',4),
('slap','Slap','Slap',6),
('rag_dung','Rag-dung','Rag-dung',102),
('orchestra','Orchestra','Orquesta',6),
('string_ensemble','String ensemble','Conjunto de cuerda',103),
('wind_ensemble','Wind ensemble','Conjunto de viento',101),
('brass_ensemble','Brass ensemble','Conjunto de metal',102),
('mixed_ensemble','Mixed ensemble','Conjunto mixto',6),
('strings','Strings','Cuerdas',103),
('viol_consort','Viol consort','Consort de violas',103);

INSERT IGNORE INTO `ensembles` (ensembles_name, ensembles_code, ensembles_description) VALUES
('A cappella','A_CAPP','Sin acompañamiento instrumental');
