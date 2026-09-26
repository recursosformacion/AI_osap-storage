# Modelo concreto de `Person` (osap-storage)

> **Estado: CERRADO — Modelo Person v1 (2026-09-22).**
> El modelo queda concretado y operativo en esquema, dominio, repositorio, API y
> administración; la migración 006 está aplicada sobre la BBDD real y se ha verificado
> el circuito escritura → BBDD → lectura. Ver §11 para el cierre y las deudas.
> Contexto de migración: `docsNew/fork-plan-migracion.md` §9.1.

## 1. Tabla `persons`

| Columna | Tipo | Default | Comentario |
|---|---|---|---|
| `persons_id` | `char(36)` |  | UUID estable y opaco; PK. |
| `persons_name` | `varchar(1024)` |  | Nombre canónico devuelto por Storage en Works. |
| `persons_visible` | `tinyint(1)` | 0 | 1 = utilizable públicamente. 0 = oculta (fusionada, atributo, etc.). |
| `persons_givenname` | `varchar(512)` | NULL | Nombre(s) desde autoridad (MusicBrainz, VIAF, etc.). |
| `persons_familyname` | `varchar(512)` | NULL | Apellido(s) desde autoridad. |
| `persons_sortname` | `varchar(1024)` | NULL | Nombre para ordenación (p. ej. "Beethoven, Ludwig van"). |
| `persons_birth_year` | `varchar(16)` | NULL | Año de nacimiento (texto: "1770", "c. 1770", "1770-1827"). |
| `persons_death_year` | `varchar(16)` | NULL | Año de fallecimiento. |
| `persons_status` | `varchar(16)` | 'active' | `active` \| `merged`. |
| `persons_review_status` | `varchar(16)` | 'not_reviewed' | Revisión de atribución: `not_reviewed`, `correct`, `incorrect`, `review_required`. |
| `persons_review_reason` | `varchar(64)` | NULL | Motivo de revisión cuando `review_status != 'correct'`. |
| `persons_reviewed_at` | `datetime(6)` | NULL | Fecha de última revisión. |
| `persons_merged_into` | `char(36)` | NULL | UUID de la persona canónica cuando `status = 'merged'`. |
| `persons_merged_at` | `datetime(6)` | NULL | Fecha de fusión. |
| `persons_source_system` | `varchar(32)` | 'maestro' | Origen de la persona canónica: `maestro` (autoridad) \| `app` (creada por el usuario). |
| `persons_created_at` | `datetime(6)` | auto | Alta. |
| `persons_updated_at` | `datetime(6)` | auto | Última actualización. |
| `persons_nationality` | `varchar(128)` | NULL | Nacionalidad desde autoridad (p. ej. "DE", "IT"). |
| `persons_image_url` | `varchar(2048)` | NULL | URL de imagen del autor. |
| `persons_type` | `varchar(32)` | 'person' | Naturaleza del **registro de persona**: `person` \| `pseudonym` \| `corporate` (y `anonymous`/`traditional`, reservados; ver §10). |
| `persons_attribution_note` | `varchar(255)` | NULL | Texto original de la atribución conservado junto a la persona (ver §10). |
| `persons_biography_*` | `text`/`varchar` | NULL | Campos de biografía (summary, era, nationality, key_works, key_fact, references, updated_at). |

### Índices relevantes
`idx_persons_name`, `idx_persons_visible`, `idx_persons_status`, `idx_persons_review_status`,
`idx_persons_merged_into`, `idx_persons_type` (006).

## 2. Tabla `persons_aliases`

| Columna | Tipo | Default | Comentario |
|---|---|---|---|
| `id` | bigint UAI |  | PK. |
| `person_id` | `char(36)` |  | FK → `persons.persons_id`. |
| `person_aliases_alias` | `varchar(1024)` |  | Nombre variante. |
| `person_aliases_normalized_alias` | `varchar(1024)` |  | Forma normalizada para resolución. |
| `person_aliases_name_type` | `varchar(32)` | 'alias' | `alias` \| `authority` \| `birth_name` \| `search_hint`. |
| `person_aliases_language_id` | `int(11)` | NULL | FK → `languages.id`. |
| `person_aliases_source` | `varchar(32)` | 'musicbrainz' | Origen: `musicbrainz` \| `authority` \| `maestro` \| `app`. |
| `created_at` | `datetime(6)` | auto |  |

Único: `(person_id, person_aliases_normalized_alias`(255))`.
Índice `idx_persons_aliases_norm` (003) para resolución por alias normalizado.

## 3. Tabla `persons_identity` (EAV de identificadores)

> Creada por `scripts/migrate_identity_fusion.sql` (§8 del fork plan).
> Sustituye a `persons_identifiers` + `persons_authority` + `persons_authority_name`.

| Columna | Tipo | Default | Comentario |
|---|---|---|---|
| `id` | bigint UAI |  | PK. |
| `persons_id` | `char(36)` | NULL | NULL = **candidato** (externo, no incorporado). |
| `identity_name` | `varchar(255)` |  | Nombre canónico en el momento de captura. |
| `identity_name_norm` | `varchar(128)` | '' | Normalizado para búsqueda. |
| `identity_type` | `varchar(24)` | '' | `wikidata_qid` \| `viaf` \| `imslp` \| `isni` \| `gnd` \| `discogs` \| `musicbrainz` \| `cluster` \| '' (fila canónica). |
| `identity_value` | `varchar(255)` | '' | Valor del identificador externo. |
| `identity_source` | `varchar(32)` | '' | `authority` \| `wikidata` \| `maestro` \| `cpdl` \| `web`. |
| `identity_is_anchor` | `tinyint(1)` | 0 | 1 = identificador elegido como **ancla de identidad**. |
| `identity_strength` | `varchar(16)` | NULL | Calidad del match: `exact` \| `alias` \| `fuzzy`. |
| `identity_channels` | `longtext` | NULL | JSON: canales de origen (para auditoría). |
| `identity_confidence` | `float` | 0.0 | Confianza (0–1). Añadido en 006. |
| `identity_retrieved_at` | `datetime(6)` | NULL | Marca de tiempo de captura. Añadido en 006. |
| `created_at` | `datetime(6)` | auto |  |

Índices: `idx_identity_person`, `idx_identity_name_norm`, `idx_identity_type_value`.

### Invariants
- **1 fila canónica** por persona/candidato: `identity_is_anchor = 1`, `identity_type = ''`.
- `persons_identity.persons_id` es opcional → permite candidatos.

## 4. Tabla `persons_evidence`

| Columna | Tipo | Default | Comentario |
|---|---|---|---|
| `id` | bigint UAI |  | PK. |
| `persons_id` | `char(36)` |  | FK → `persons`. |
| `persons_evidence_rule` | `varchar(64)` |  | Regla que resolvió: `creation` \| `resolution` \| `review` \| `merge` \| `cleanup` \| ID de regla (p. ej. `07-viaf-multi-anchor`). |
| `persons_evidence_decision` | `varchar(16)` |  | `resolved` \| `ambiguous` \| `not_found` \| `auto_correct` \| `pending_human` \| `rejected`. |
| `persons_evidence_reason` | `varchar(64)` |  | Motivo legible. |
| `persons_evidence_anchor_type` | `varchar(24)` | 'none' | `work` \| `batch` \| `name` \| `none`. |
| `persons_evidence_anchor_value` | `varchar(255)` | 'none' | ID o valor del ancla. |
| `persons_evidence_channels` | `longtext` | NULL | JSON. |
| `persons_evidence_identifiers_used` | `longtext` | NULL | JSON; para `creation`/`resolution` almacena el *payload* completo (work_id, extracted_author, etc.). |
| `persons_evidence_matcher_version` | `varchar(32)` |  | Versión del matcher/resolver. |
| `persons_evidence_created_at` | `datetime(6)` | auto |  |

## 5. Entidades de dominio (`domain/entities/person.py`)

### `Person`
```python
@dataclass
class Person:
    id: str
    name: str
    musicbrainz_id: str | None
    homepage: str | None
    status: str                    # PersonStatus
    visible: bool
    birth_year: str | None
    death_year: str | None
    given_name: str | None         # persons_givenname
    family_name: str | None        # persons_familyname
    sort_name: str | None          # persons_sortname
    nationality: str | None        # persons_nationality
    image_url: str | None          # persons_image_url
    person_type: str               # PersonType (persons_type)
    attribution_note: str | None   # persons_attribution_note
    cluster_id: str | None
    review_reason: str | None
    source_system: str
    merged_into: str | None
    merged_at: datetime | None
    review_status: str
    reviewed_at: datetime | None
    suspicious: bool
    suspicious_reason: str | None
    created_at: datetime | None
    updated_at: datetime | None
```

### `PersonIdentifier` (frozen)
```python
@dataclass(frozen=True)
class PersonIdentifier:
    person_id: str
    id_type: str
    id_value: str
    is_identity_anchor: bool
    source: str
    strength: str | None
    channels: list[str] | None
    confidence: float             # identity_confidence (006)
    retrieved_at: datetime | None # identity_retrieved_at (006)
```

### `PersonSummary` (frozen)
Fila ligera del listado. Incluye `given_name`, `family_name`, `sort_name`,
`nationality`, `person_type` (añadidos 2026-09-22).

### `PersonDetail` (frozen)
Detalle administrativo. Incluye todos los campos de `Person` + aliases,
identifiers, evidence, creation_evidence, biography fields.

### Constantes y enums
- `UNKNOWN_PERSON` / `UNKNOWN_PERSON_ID` — "Compositor sin indicar".
- `PersonStatus`: `ACTIVE`, `MERGED`.
- `PersonType`: `PERSON`, `PSEUDONYM`, `CORPORATE` (+ `ANONYMOUS`, `TRADITIONAL`, reservados; ver §10).
- `PersonResolutionDecision`: `RESOLVED`, `AMBIGUOUS`, `NOT_FOUND`, `AUTO_CORRECT`, `PENDING_HUMAN`, `REJECTED`.

## 6. Mapeo SQL ←→ Entidad (`SqlPersonRepository`)

| Entidad | Columnas SQL |
|---|---|
| `_COMPOSER_COLS` | `persons_*` (incl. `persons_givenname`, `persons_familyname`, `persons_sortname`, `persons_nationality`, `persons_image_url`, `persons_type`, `persons_attribution_note`) |
| `_IDENTIFIER_COLS` | `persons_identity.*` (incl. `identity_confidence`, `identity_retrieved_at`) |
| `update_composer` | SET dinámico sobre `persons.*` + alias INSERT IGNORE + identificador (musicbrainz/cluster) |
| `get_detail` | SELECT canónico + aliases + identifiers + evidence |

### Compatibilidad
`composer.py` re-exporta `Person*` como `Composer*`, `ComposerRepository` como puerto,
`SqlComposerRepository = SqlPersonRepository`.

## 7. API pública (`api/schemas.py`)

- **`PersonSummaryRead`**: `id`, `name`, `sort_name`, `roles`, `works_count`,
  `aliases_count`, `birth_year`, `death_year`, `visible`, `review_status`,
  `person_type`, `nationality`, `image_url`, `biography_*`.
- **`PersonPublicRead`**: extensión de `PersonSummaryRead` con `given_name`,
  `family_name`, `attribution_note`, `biography_key_works`, `biography_key_fact`, `aliases`.
- **`PersonWorkRead`**: obra vista por persona (`work_id`, `title`, `roles`, `genres`, `instruments`).

## 8. Roles (`roles` + `roles_categoria` + `works_person_roles`)

15 roles definidos. `works_person_roles` enlaza persona-obra-rol.
El rol 1 (`composer`) es el rol de compositor principal. La API expone los
roles por clave inglesa (`composer`, `arranger`, `performer`, `editor`…)
traducidos con `domain/services/person_roles.py`.

## 9. Migración 006

`006_person_model_refinement.sql` añade:
- `persons_nationality`, `persons_image_url`, `persons_type`, `persons_attribution_note`.
- `identity_confidence`, `identity_retrieved_at` en `persons_identity`.
- Índice `idx_persons_type`.

Es idempotente (`ADD COLUMN IF NOT EXISTS` / `ADD INDEX IF NOT EXISTS`, MariaDB).
**No registra la migración en `schema_migrations`**: de eso se encarga exclusivamente
el runner (`infrastructure/db/migrate.py`). Registrarla dentro del fichero rompe el runner
con `Duplicate entry` (bug corregido el 2026-09-22).

## 10. Semántica: `persons_type` ≠ `works_attr_type`

Son conceptos **independientes** y no se unifican.

- **`persons.persons_type`** — naturaleza del *registro de persona*:
  - `person`: persona real (individual).
  - `pseudonym`: nombre artístico sin identidad civil conocida.
  - `corporate`: entidad colectiva (orquesta, institución, editorial).
  - `anonymous` / `traditional`: **reservados**. Se mantienen en el enum por
    compatibilidad/modelo futuro, pero **no se crean automáticamente registros en
    `persons` de estos tipos** (no representan personas reales).

- **`works.works_attr_type`** — naturaleza/estado de la *atribución de una obra*
  (`ANONIMA`, `TRADICIONAL`, `POPULAR`, `ATRIBUIDA`, `DESCONOCIDO`). Vive en la obra y
  no genera registros artificiales en `persons`.

Por tanto:

- `works_attr_type = 'ANONIMA'` **no** implica crear `Person("Anónimo")`.
- `works_attr_type = 'TRADICIONAL'` **no** implica crear `Person("Tradicional")`.

`set_attribution()` y `mark_anonymous_attr.py` escriben `works.works_attr_type` y no
`persons_type`: es lo correcto bajo este criterio.

Nota: el `PUT /api/admin/composers/{id}` sigue aceptando `anonymous`/`traditional` por
validación del enum, pero **ningún pipeline los asigna automáticamente**; fijarlos es una
decisión manual del administrador y no el flujo normal de alta.

## 11. Cierre de fase

**FASE PERSON — CERRADA (concretización del modelo Person v1).**

Cerrado y verificado:

- Modelo de dominio `Person` y `PersonIdentifier` (campos nuevos incluidos).
- Persistencia de los campos nuevos (`_COMPOSER_COLS`, `_IDENTIFIER_COLS`,
  `_row_to_composer`, `_row_to_identifier`, `update_composer`, `add_identifier`,
  `get_detail`, merge) y migración 006 aplicada en MariaDB con `idx_persons_type`.
- API y administración (`PersonSummaryRead`, `PersonPublicRead`, `ComposerAdminDetail`,
  `ComposerIdentifierRead`, `ComposerUpdateRequest` y `PUT /api/admin/composers/{id}`).
- Verificación real: escritura → BBDD → lectura de `person_type` (no revierte a `person`);
  identidad con `confidence=0.92` y `retrieved_at` recuperados por el detalle; 257 tests;
  `ruff` limpio.
- Circuito demostrado: API → use case → repository → MariaDB → repository → API.

**Fuera de esta fase (no bloqueante).** Que los campos nuevos estén vacíos
(`persons_type = 'person'` en 45.226 personas; `nationality`/`image_url`/`attribution_note`
a NULL; `identity_confidence = 0` en 114.194 identidades) significa que los pipelines de
enriquecimiento aún no los consumen, no que la concretización esté incompleta.

Deudas registradas (fases posteriores):

| Deuda | Circuito |
|---|---|
| Fuente de `nationality` y `image_url` | Enriquecimiento de Person |
| Quién determina `persons_type` en el alta | Enriquecimiento de Person |
| Cálculo de `identity_confidence` por los resolvers | Resolución/identidad |
| `update_composer` no distingue "no enviado" de "enviado a NULL" | Mejora administrativa |
| Documentar `not_reviewed_1/2/3` como valores que produce `mark_persons_difficulty.py`, no del CRUD | Documentación / osap-api |
| `set_attribution()` deja `status='merged'` con `merged_into=NULL` | Circuito de atribución |
| 158.922 works sin rol 1 y sin `works_attr_type` | Circuito de atribución de obras |

Relación formal entre vocabularios: documentada en §10, **sin fusionar** hasta demostrar
que representan el mismo concepto.

