# Migraciones — fork `osap-storage` (esquema nuevo)

Estado: la BBDD `osap-storage` **ya tiene el esquema nuevo aplicado**. No hay baseline
versionado todavía.

- Las migraciones **001–041 pertenecen al esquema viejo** (`osap-storage_v1`) y están
  archivadas en `../migrations_v1/`. **No deben aplicarse** sobre la nueva.
- Este directorio queda vacío a propósito: el siguiente paso de la Fase 6 es **generar el
  baseline** del esquema actual y empezar de nuevo desde `001_...`.

Cómo generar el baseline (solo estructura, sin datos):

```powershell
mysqldump -h 127.0.0.1 -u osap2027 -p --no-data --skip-comments --routines=false `
  "osap-storage" > infrastructure/db/migrations/001_baseline_schema.sql
```

El runner (`infrastructure/db/migrate.py`) aplica los `.sql` de este directorio en orden
alfabético y registra cada uno en `schema_migrations`; sigue siendo válido tal cual.
