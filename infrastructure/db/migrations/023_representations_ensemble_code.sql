-- 023: contexto de formación en `representations` (Bloque 3).
-- Autoridad: representations.representations_ensemble_code -> ensembles.ensembles_code
-- (id_canonico) -> ensemble_voices. `representations_voice_signature` es un dato DERIVADO
-- para búsqueda (no fuente de verdad). Ver docs/osap/ensemble-canonical-model.md.
ALTER TABLE `representations`
  ADD COLUMN `representations_ensemble_code` VARCHAR(64) DEFAULT NULL
    COMMENT 'id_canonico de la formacion (ensembles.ensembles_code)'
    AFTER `representations_license`,
  ADD COLUMN `representations_voice_signature` VARCHAR(64) DEFAULT NULL
    COMMENT 'firma de frecuencias derivada de ensemble_voices (p.ej. S2A2T2B2), solo busqueda'
    AFTER `representations_ensemble_code`,
  ADD KEY `idx_representations_ensemble_code` (`representations_ensemble_code`);
