# osap-storage — Service Authorization Preparation v1

**Estado:** PREPARACIÓN. **No implementado.**
**Base:** `docs/service-auth-v1.md`, `docs/provider-api-contract.md`,
`docs/voting-statistics-v1.md`, `docs/composer-administration-v1.md`.

---

# 1. Estado actual

- osap-storage es **ajeno a usuarios**: no valida JWT de usuario, no conoce email,
  contraseñas, sesiones, roles ni autenticación de usuarios.
- Acepta únicamente **tokens de servicio** con scope `storage:read` (según `service-auth-v1.md`).
- El contrato Provider API (search/lookup/resource/download/version) exige service token.
- Votos, estadísticas y compositores viven en storage; el recálculo y la regla de unicidad
  (1 voto/obra/día) son responsabilidad del modelo de datos de storage.

## Confirmación de no-dependencia de usuario

- No se ha encontrado validación de identidad de usuario en los contratos de storage.
- El `user_id` aparece únicamente como **dato de negocio** en `votes.user_id`
  (`voting-statistics-v1.md`): storage lo guarda como UUID opaco sin resolverlo contra
  osap-auth.

---

# 2. Scopes

Existentes:
- `storage:read` — leer Works, compositores, recursos (search/lookup/resource/download) y
  estadísticas.

Futuros (documentar, **no crear todavía** salvo que estén definidos normativamente):

| Scope futuro | Operaciones | Notas |
|---|---|---|
| `storage:write` | votos (`POST /api/v1/works/{id}/votes`), escritura de datos | no ampliar `storage:read` |
| `storage:admin` | `/api/admin/composers*` (listar, detalle, works, merge), fusiones, operaciones administrativas | administrativo |

`service-auth-v1.md` ya indica que si se necesita escritura se añaden scopes dedicados.

---

# 3. Matriz de operaciones (osap-storage)

| Operación | Principal | Scope | user_id | Anónimo | Notas |
|---|---|---|---|---|---|
| `GET /api/search`, `/lookup`, `/resource/{id}`, `/download/{id}`, `/version` | SERVICE | `storage:read` | no | no | llamada por osap-api |
| `POST /api/v1/works/{work_id}/votes` | SERVICE | `storage:read` (+futuro `storage:write`) | **sí (dato)** | no | `user_id` en el payload |
| `GET /api/v1/works/{id}/statistics`, `/composers/{id}/statistics` | SERVICE | `storage:read` | no | no | |
| `GET /api/admin/composers` | SERVICE | `storage:read` / futuro `storage:admin` | no | no | administrativo |
| `GET /api/admin/composers/candidates` | SERVICE | futuro `storage:admin` | no | no | |
| `GET /api/admin/composers/{id}`, `/{id}/works` | SERVICE | futuro `storage:admin` | no | no | |
| `POST /api/admin/composers/{target}/merge` | SERVICE | futuro `storage:admin` | no | no | fusión |
| `recompute-statistics`, `backfill-composer-ids`, `populate-composers` | INTERNAL_PROCESS | — | no | — | CLI local (cron/systemd) |

---

# 4. user_id como dato de negocio

El hecho de que storage reciba un `user_id` **no** lo convierte en sistema de identidad.

Ejemplo:
```
POST /api/v1/works/{work_id}/votes
  SERVICE = osap-api
  payload = { "user_id": "<UUID>", "vote": 5 }
```

- El `user_id` es una **referencia de negocio** para el voto (regla de unicidad, agregado).
- Storage **no** lo resuelve contra osap-auth ni lo usa para autorizar.

---

# 5. Flujos

- **Público:** ANONYMOUS → osap-api → (SERVICE `storage:read`) → osap-storage.
- **Autenticado:** USER → osap-api → (SERVICE) → osap-storage; `user_id` viaja como dato de
  negocio si es necesario.
- **Administrativo:** USER+admin → osap-api → (SERVICE + `storage:admin`) → osap-storage.
- **Interno:** INTERNAL_PROCESS → osap-storage (CLI local; sin sistema nuevo todavía).

---

# 6. Administración de compositores

`/api/admin/composers*` es administrativo. `composer-administration-v1.md` (§Autorización)
indica que el enforcement queda preparado (prefijo `/api/admin/`, campo `merged_by`) sin
sistema de autorización nuevo. Cuando se cablee el auth administrativo, esta sección debe
protegerse (scope `storage:admin`).

---

# 7. Cuestiones pendientes de osap-storage

1. Definir y aprobar `storage:write` (votos) y `storage:admin` (compositores/fusiones).
2. Aplicar enforcement administrativo a `/api/admin/composers*`.
3. Confirmar explícitamente en el código que no existe validación de identidad de usuario.

---

# 8. Cambios futuros necesarios

- Añadir `storage:write` y proteger el POST de votos.
- Añadir `storage:admin` y proteger `/api/admin/composers*`.
- Mantener la regla de unicidad de votos en la BD.

---

*Documento de preparación de autorización de servicio de osap-storage v1 (2026-08) — no implementado.*
