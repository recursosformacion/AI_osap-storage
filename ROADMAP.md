# ROADMAP — osap-storage (Servidor de datos autoritativo)

Rol en la arquitectura: **servidor de datos del catálogo** (obras, compositores,
relaciones, votos, estadísticas, resources/ficheros). No es una API pública de negocio:
solo acepta llamadas autorizadas de servicios (JWT de servicio + scopes).

Roadmap global de referencia: `_docs/roadmap.md` (raíz del proyecto).

---

## Fase A — Seguridad (P0) — PRIORIDAD

| Tarea | Estado |
|---|---|
| JWT RS256, JWKS de osap-auth, `iss`, `aud`, `exp`, `token_use=service`, scopes | 🟡 Implementado |
| Middleware protect-all-by-default (`auth.enabled=true` en prod) | 🟡 Pendiente de desplegar |
| Scopes `storage:read` / `storage:write` / `storage:admin` | 🟡 Implementado |
| Reglas: GET→read; POST/PUT/PATCH/DELETE→write; `/api/admin/*`→admin; merge→admin | 🟡 Implementado |
| `/health` y `/metrics` como excepciones | 🟡 Pendiente de confirmar |
| Confirmar JWKS efectiva y `audience` de storage | 🟡 Pendiente |
| Probar: llamadas autorizadas, rechazo sin token, scopes insuficientes | 🟡 Pendiente |

**Criterio:** desde Internet no se puede leer ni modificar storage sin un JWT de servicio válido.

## Fase D — Catálogo (P4, P5)

- Calidad de identidad de compositores (~35.000): distinguir extraído / catálogo / revisado /
  alias / identidad canónica.
- Exponer obras por `composer_id` como ruta válida para el pipeline (consistencia
  compositor → obras → representaciones).
- Revisión como proceso de calidad del catálogo (no solo merges).

## Fase G — Operación

| Tarea | Prioridad | Estado |
|---|---|---|
| Observabilidad (requests, rechazos de auth, scopes, errores, escrituras, operaciones admin) | P11 | 🟡 En evolución |
| Tests de contrato osap-api ↔ osap-storage (JWT servicio, scopes, read/write/admin, rechazo sin/con token incorrecto) | P13 | 🟡 Pendiente |
| Despliegue separado (Servidor A/B/C) | P14 | 🟡 En evolución |
| Limpieza de configuración | P15 | 🟡 Pendiente |

---

## Estado actual

| Área | Estado |
|---|---|
| Catálogo (obras/compositores/relaciones/votos/estadísticas) | ✅ |
| Auth de servicio (JWT RS256, JWKS, scopes) | 🟡 Implementado |
| `auth.enabled=true` en prod | 🟡 Pendiente de desplegar |
| Rechazo de llamadas sin JWT | 🟡 Pendiente de confirmar |
| Calidad de compositores | 🟡 Pendiente |
| Consistencia composer → works | 🟡 Pendiente |
| Observabilidad | 🟡 En evolución |

---

## Criterio de cierre

- Storage solo acepta llamadas de servicios autorizados con JWT válido y scope suficiente.
- osap-api lee/escribe el catálogo como servicio; el Web nunca accede a storage directamente.

*Fuente: `_docs/roadmap.md` (fases A, D, G).*
