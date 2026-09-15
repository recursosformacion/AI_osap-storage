import type { SchemaColumn } from './api'

export interface TableMeta {
  label: string
  group: string
  /** Columnas "importantes" en orden de relevancia (vacío = usar las primeras del schema). */
  columns?: string[]
}

export const GROUPS = [
  'Personas',
  'Obras',
  'Música y catálogos',
  'Almacenamiento',
  'Sistema',
] as const

export const TABLES: Record<string, TableMeta> = {
  // ---------------------------------------------------------------- Personas
  persons: {
    label: 'Personas',
    group: 'Personas',
    columns: [
      'persons_id', 'persons_name', 'persons_status', 'persons_review_status',
      'persons_visible', 'persons_birth_year', 'persons_death_year',
    ],
  },
  persons_aliases: {
    label: 'Alias de personas',
    group: 'Personas',
    columns: [
      'id', 'person_id', 'person_aliases_alias', 'person_aliases_normalized_alias',
      'person_aliases_name_type', 'person_aliases_source',
    ],
  },
  persons_authority: {
    label: 'Autoridad',
    group: 'Personas',
    columns: [
      'authority_id', 'persons_id', 'persons_authority_canonical_name',
      'persons_authority_wikidata_id', 'persons_authority_viaf_id',
      'persons_authority_imslp_id',
    ],
  },
  persons_authority_name: {
    label: 'Nombres de autoridad',
    group: 'Personas',
    columns: [
      'id', 'authority_id', 'persons_authority_name_name',
      'persons_authority_name_normalized_name', 'persons_authority_name_source',
    ],
  },
  persons_evidence: {
    label: 'Evidencia',
    group: 'Personas',
    columns: [
      'id', 'persons_id', 'persons_evidence_rule', 'persons_evidence_decision',
      'persons_evidence_reason', 'persons_evidence_anchor_value',
    ],
  },
  persons_identifiers: {
    label: 'Identificadores',
    group: 'Personas',
    columns: [
      'id', 'persons_id', 'persons_identifiers_type', 'persons_identifiers_value',
      'persons_identifiers_source', 'persons_identifiers_is_identity_anchor',
    ],
  },
  persons_merge_history: {
    label: 'Historial de fusiones',
    group: 'Personas',
    columns: ['id', 'source_person_id', 'target_person_id', 'merged_at', 'merged_by'],
  },

  // ------------------------------------------------------------------- Obras
  works: {
    label: 'Obras',
    group: 'Obras',
    columns: [
      'id', 'works_title', 'works_origin', 'works_origin_id', 'works_catalogue',
      'works_year', 'works_license',
    ],
  },
  works_person_roles: {
    label: 'Obra ↔ persona ↔ rol',
    group: 'Obras',
    columns: [
      'works_person_roles_id', 'works_person_roles_work_id',
      'works_person_roles_person_id', 'works_person_roles_role_id',
      'works_person_roles_order',
    ],
  },
  works_person_import: {
    label: 'Import de personas (staging)',
    group: 'Obras',
    columns: [
      'id', 'works_id', 'works_person_import_name', 'works_person_import_role',
      'works_person_import_source', 'works_person_import_resolved',
    ],
  },
  work_parts: {
    label: 'Partes de obra',
    group: 'Obras',
    columns: ['id', 'works_id', 'work_parts_name'],
  },
  work_statistics: {
    label: 'Estadísticas de obra',
    group: 'Obras',
    columns: [
      'works_id', 'wksta_vote_count', 'wksta_work_count', 'wksta_rating',
      'wksta_adjusted_rating', 'wksta_confidence',
    ],
  },

  // ------------------------------------------------------- Música y catálogos
  instruments: {
    label: 'Instrumentos',
    group: 'Música y catálogos',
    columns: ['id', 'code', 'name_en', 'name_es', 'category_id'],
  },
  instrument_categories: {
    label: 'Familias de instrumentos',
    group: 'Música y catálogos',
    columns: ['id', 'code', 'name', 'parent_id'],
  },
  voices: {
    label: 'Voces',
    group: 'Música y catálogos',
    columns: ['id', 'voices_name', 'voices_sort'],
  },
  ensembles: {
    label: 'Conjuntos',
    group: 'Música y catálogos',
    columns: ['id', 'ensembles_code', 'ensembles_name', 'ensembles_description'],
  },
  genres: { label: 'Géneros', group: 'Música y catálogos', columns: ['id', 'name'] },
  genre_mappings: {
    label: 'Mapeo de géneros',
    group: 'Música y catálogos',
    columns: ['code', 'genre_id'],
  },
  epochs: { label: 'Épocas', group: 'Música y catálogos' },
  languages: {
    label: 'Idiomas',
    group: 'Música y catálogos',
    columns: ['id', 'languages_code', 'languages_name'],
  },
  roles: { label: 'Roles', group: 'Música y catálogos' },
  category: { label: 'Categorías', group: 'Música y catálogos' },
  categoryrol: { label: 'Categoría ↔ rol', group: 'Música y catálogos' },
  tag_work: {
    label: 'Etiquetas',
    group: 'Música y catálogos',
    columns: ['id', 'tag_texto', 'tag_descripcion'],
  },
  catalog: {
    label: 'Catálogos (regex/formato)',
    group: 'Música y catálogos',
    columns: ['id', 'catalog_id', 'catalog_name', 'catalog_format_template'],
  },

  // ---------------------------------------------------------- Almacenamiento
  archives: {
    label: 'Archivos (tar)',
    group: 'Almacenamiento',
    columns: ['id', 'name', 'format', 'status', 'size'],
  },
  archive_entries: {
    label: 'Entradas de archivo',
    group: 'Almacenamiento',
    columns: ['id', 'archive_id', 'work_id', 'file_id', 'relative_path', 'size', 'status'],
  },
  files: {
    label: 'Ficheros',
    group: 'Almacenamiento',
    columns: ['id', 'sha256', 'name', 'mime_type', 'size_bytes', 'status'],
  },
  storage_locations: {
    label: 'Ubicaciones',
    group: 'Almacenamiento',
    columns: ['id', 'file_id', 'provider_id', 'object_key', 'status'],
  },
  storage_providers: {
    label: 'Proveedores',
    group: 'Almacenamiento',
    columns: ['id', 'name', 'provider_type', 'enabled'],
  },
  import_sources: {
    label: 'Fuentes de importación',
    group: 'Almacenamiento',
    columns: ['id', 'provider', 'version', 'csv_path', 'imported_at'],
  },
  download_jobs: {
    label: 'Trabajos de descarga',
    group: 'Almacenamiento',
    columns: ['id', 'file_id', 'provider_id', 'status', 'error_message'],
  },
  statistics: {
    label: 'Estadísticas',
    group: 'Almacenamiento',
    columns: ['id', 'archives', 'entries', 'files', 'bytes', 'computed_at'],
  },
  statistics_runs: {
    label: 'Ejecuciones de estadísticas',
    group: 'Almacenamiento',
    columns: ['id', 'started_at', 'finished_at', 'works_updated', 'composers_updated'],
  },

  // ---------------------------------------------------------------- Sistema
  authority_sync_state: {
    label: 'Estado de sincronización',
    group: 'Sistema',
    columns: ['source', 'last_packet', 'last_success_at', 'last_error'],
  },
  schema_migrations: {
    label: 'Migraciones',
    group: 'Sistema',
    columns: ['id', 'name', 'applied_at'],
  },
  votes: {
    label: 'Votos',
    group: 'Sistema',
    columns: ['id', 'user_id', 'work_id', 'vote', 'vote_day'],
  },
}

export function metaOf(table: string): TableMeta {
  return TABLES[table] ?? {
    label: table,
    group: 'Sistema',
  }
}

/** Columnas a mostrar en el listado: las curadas, o las primeras del schema. */
export function displayColumns(table: string, schema: SchemaColumn[], max = 7): string[] {
  const meta = TABLES[table]
  if (meta?.columns?.length) return meta.columns
  return schema.filter((c) => c.name !== 'works_voicing' && c.name !== 'works_instrumentation')
    .slice(0, max)
    .map((c) => c.name)
}

export function groupTables(tables: string[]): { group: string; tables: string[] }[] {
  return GROUPS.map((group) => ({
    group,
    tables: tables
      .filter((t) => metaOf(t).group === group)
      .sort((a, b) => metaOf(a).label.localeCompare(metaOf(b).label, 'es')),
  })).filter((g) => g.tables.length > 0)
}
