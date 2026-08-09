# OSAP-Storage — Service Authentication (v1)

**Estado:** CONGELADO v1.
**Depende de:** `osap-auth/docs/osap-auth-api-v1.0.md`.

---

# 1. Principio

**osap-storage es ajeno a usuarios.**

No necesita saber quién es el usuario, qué permisos tiene ni qué rol posee. Solo necesita
saber una cosa de cada petición:

> "Esta petición procede de un **servicio autorizado**."

La única identidad relevante para osap-storage es la del **servicio que la llama** (osap-api),
nunca la del usuario final.

---

# 2. Arquitectura de confianza

```text
                 ┌──────────────┐
                 │  osap-auth   │
                 │              │
                 │ usuarios     │
                 │ sesiones     │
                 │ email        │
                 │ credenciales │
                 └──────┬───────┘
                        │
                  user identity
                        │
                        ▼
                 ┌──────────────┐
                 │   osap-api   │
                 │              │
                 │ votos        │
                 │ estadísticas │
                 │ resolución   │
                 └──────┬───────┘
                        │
                  service auth
                        │
                        ▼
                 ┌──────────────┐
                 │ osap-storage │
                 │              │
                 │ Works        │
                 │ compositores │
                 │ resources    │
                 │ ficheros     │
                 └──────────────┘
```

- `user identity` viaja de osap-auth a osap-api.
- `service auth` viaja de osap-api a osap-storage.
- osap-storage **nunca** recibe identidad de usuario.

---

# 3. Lo que osap-storage acepta

osap-storage acepta únicamente **tokens de servicio** (JWT emitidos por `client_credentials` de
osap-auth) con el scope adecuado.

## Validación

1. Firma JWT contra el **JWKS** de osap-auth.
2. `iss == osap-auth`.
3. `aud == osap-storage` (o scope específico).
4. `scope` contiene `storage:read`.
5. `exp` válido (+ tolerancia de *clock skew*).

## Lo que osap-storage rechaza

- **Tokens de usuario** (access tokens de usuario final): rechazados. Un token de usuario
  filtrado jamás debe dar acceso a storage.
- Peticiones sin token de servicio o sin el scope `storage:read`.

---

# 4. Scopes de storage

| Scope | Concede |
|-------|---------|
| `storage:read` | leer Works, compositores y recursos (search/lookup/resource/download) |

Si en el futuro osap-storage necesita operaciones de escritura, se añaden scopes dedicados
(`storage:write`) con su propia política. No se amplía un scope de lectura.

---

# 5. Exposición y red

- osap-storage **no debe exponerse directamente a Internet** como servicio de consumo
  general.
- Solo accesible internamente (red privada / mTLS / firewall de servicio) desde servicios
  autorizados (osap-api).
- El acceso externo, si existe, debe estar protegido y controlado por osap-auth/osap-api,
  no expuesto directamente.

---

# 6. Qué conoce y qué no conoce osap-storage

## Conoce

- Obras (Works), compositores, recursos físicos, metadata, enlaces de descarga.
- La identidad del **servicio** llamante (para autorizar), nunca la del usuario.

## No conoce (ni debe conocer)

- Identidad del usuario final (`user_id`, `email`, `roles`).
- Sesiones o tokens de usuario.
- Permisos del usuario.
- Relación entre una petición y una persona.

---

# 7. Errores y códigos esperados

| Código | Significado |
|--------|-------------|
| 401 | Token de servicio ausente/inválido/caducado |
| 403 | Token válido pero sin scope `storage:read` |
| 404 | Work/recurso no encontrado |

---

# 8. Consecuencia para el contrato existente

El contrato `provider-api-contract.md` se mantiene como está (search/lookup/resource/download),
con el **añadido** de que todas sus rutas exigen ahora un **token de servicio** con
`storage:read`. Los DTOs no cambian.

---
*Documento de autenticación de servicio para osap-storage (v1, 2026-08).*
