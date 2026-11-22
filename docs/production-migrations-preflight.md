# Preflight de migraciones de producción (API, Auth y Storage)

**Propósito:** distinguir las migraciones pendientes de los artefactos históricos y fijar las condiciones verificables antes de tocar producción.

**Límite de esta nota:** no se ha conectado a producción ni se ha ejecutado ninguna migración. Los estados de las bases de datos que se atribuyen a la revisión de DeepSeek son resultados comunicados por el equipo, no verificaciones independientes de este documento.

## 1. Artefacto histórico que NO debe ejecutarse

`scripts/migrate_to_new.sql` es una conversión puntual de datos V1→V3, creada el 15-09-2026. Vacía 29 tablas del destino mediante `TRUNCATE` y copia datos desde `osap-storage_v1`. No forma parte del runner de migraciones: está en `scripts/`, mientras que `infrastructure/db/migrate.py` solo busca SQL en `infrastructure/db/migrations/`.

**Estado: OBSOLETO. No ejecutar en despliegues actuales ni como migración V6.** Se conserva para auditoría histórica. La conversión V6 tiene su propio diseño y sus scripts `v6_*`.

## 2. Migraciones pendientes que sí corresponden a los servicios actuales

| Servicio | Migración | Qué hace | Condición obligatoria antes de aplicar |
|---|---|---|---|
| OSAP-API | `migrations/001_baseline_schema.sql` | Baseline de esquema con 49 `CREATE TABLE IF NOT EXISTS`; no importa datos ni corrige columnas/índices existentes. | Comparar el esquema real completo con el baseline. No confundir `IF NOT EXISTS` con reparación de drift. La copia dev descrita en la revisión no coincide con el baseline y no sirve para validar producción. |
| OSAP-Auth | Alembic `0020_user_avatar` | Añade `users.avatar_data TEXT NULL`. | Solo ejecutar si Alembic está en `0019_nickname_unique` **y** la columna `users.avatar_data` no existe. No es idempotente. Si la columna ya existe con Alembic en 0019, detenerse y reconciliar antes de actualizar. |
| OSAP-Storage | `029_enrichment.sql` | Crea `enrichment_candidates` y `enrichment_applied`. | Comparar el `SHOW CREATE TABLE` de ambas tablas productivas con el SQL versionado. Solo después registrar/aplicar 029. `CREATE TABLE IF NOT EXISTS` no corrige definiciones distintas. |

### 2.1 OSAP-API — baseline

El fichero versionado contiene 49 tablas. El runner `script/migrate_api.py` crea `schema_migrations`, aplica los SQL pendientes en orden y registra cada fichero. Si 001 aún no está registrada, ejecutará los 49 `CREATE TABLE IF NOT EXISTS`.

Antes de ejecutarlo en producción:
1. Confirmar que la base seleccionada es `osap_api`.
2. Comparar las 49 tablas, columnas, tipos, nulabilidad, claves, índices y restricciones de la BD con `migrations/001_baseline_schema.sql`.
3. Confirmar específicamente los índices únicos `uq_idx_public_id` y `uq_idx_title_composer` de `index_works`.
4. Si el esquema coincide, ejecutar el runner y comprobar que `001_baseline_schema.sql` queda registrada en `schema_migrations`.
5. Si hay diferencias, no registrar el baseline como aplicado ni confiar en `IF NOT EXISTS`: preparar una corrección explícita y revisada.

La divergencia de la copia local dev comunicada (48 tablas y tablas experimentales adicionales) no debe “arreglarse” copiando o eliminando tablas en producción. Es una divergencia de esa copia, no evidencia de que producción esté mal.

### 2.2 OSAP-Auth — revisión 0020

La revisión versionada hace exactamente:

```python
op.add_column("users", sa.Column("avatar_data", sa.Text(), nullable=True))
```

Preflight:

```sql
SELECT version_num FROM alembic_version;
SELECT COUNT(*) AS avatar_data_exists
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'users'
  AND column_name = 'avatar_data';
```

Solo el estado `0019_nickname_unique` + `avatar_data_exists = 0` autoriza `alembic upgrade head`. Después deben observarse `0020_user_avatar` y `avatar_data_exists = 1`. Si la columna existe ya, no se debe ejecutar la revisión a ciegas.

### 2.3 OSAP-Storage — migración 029

El runner `infrastructure/db/migrate.py` aplica los SQL pendientes de `infrastructure/db/migrations/` en orden y registra el nombre en `schema_migrations`. La migración 029 usa `CREATE TABLE IF NOT EXISTS` para ambas tablas.

Preflight:

```sql
SELECT MAX(name) AS ultima, COUNT(*) AS n FROM schema_migrations;
SHOW CREATE TABLE enrichment_candidates;
SHOW CREATE TABLE enrichment_applied;
```

Comprobar además que existen las dos tablas, que `enrichment_candidates` tiene la clave única `uq_enrich` y que todas las columnas, tipos, nulabilidad e índices coinciden con 029. Si coinciden y 029 no está registrada, el runner puede registrar la migración sin recrear ni vaciar esas tablas. Si no coinciden, detenerse: `IF NOT EXISTS` no actualiza tablas existentes.

## 3. Evidencias comunicadas por la revisión independiente

Los siguientes resultados proceden del informe de DeepSeek compartido por el equipo; no se presentan como ejecuciones propias ni como comprobaciones actuales de producción:

- API: baseline de 49 tablas; copia dev con 48 tablas y objetos experimentales adicionales; índices únicos mencionados presentes en la comprobación descrita.
- Auth: copia dev en revisión 0020 y columna `avatar_data` presente; producción se indicó en 0019.
- Storage: copia dev en 028 y sin las dos tablas 029; se comunicó que las tablas productivas existen y que sus definiciones se contrastaron con `SHOW CREATE`, pero 029 no está registrada.
- Tests comunicados: API 967 passed / 2 skipped; Auth 210; Support 207; Storage 599 / 47 skipped; Publicidad 55; Blog 27; Videos 10; Noticias 40.

Estos resultados son evidencia útil, pero no sustituyen el preflight sobre la instancia productiva concreta inmediatamente antes del despliegue.

## 4. Orden de actuación recomendado

1. Hacer backup verificable de las tres bases y comprobar que puede restaurarse.
2. Ejecutar únicamente las consultas de preflight de API, Auth y Storage.
3. Resolver cualquier discrepancia de esquema antes de aplicar nada.
4. Aplicar API baseline solo tras comparar el esquema completo.
5. Aplicar Storage 029 solo tras comparar los dos `SHOW CREATE TABLE` y confirmar que no está registrada.
6. Aplicar Auth 0020 solo si versión y ausencia de columna cumplen exactamente la precondición.
7. Repetir las consultas de verificación y conservar las salidas como evidencia del despliegue.

**No se incluye aquí ninguna orden para ejecutar `scripts/migrate_to_new.sql`. Ese archivo queda expresamente fuera del procedimiento.**
