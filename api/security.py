from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import httpx
import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Scopes de servicio definidos en service-auth-v1 / osap-auth.
SCOPE_READ = "storage:read"
SCOPE_WRITE = "storage:write"
SCOPE_ADMIN = "storage:admin"

# Rutas exentas de autenticación (salud y métricas operativas).
EXEMPT_PATHS = {"/api/v1/health", "/metrics"}


class ServiceTokenValidator:
    """Valida JWT de servicio emitidos por osap-auth.

    Reglas (service-auth-v1):
    - firma verificada (RS256) contra el JWKS de osap-auth (o clave pública configurada);
    - `iss` == issuer configurado;
    - `aud` == audience configurada;
    - `token_use` == "service" (rechaza tokens de usuario);
    - `exp` válido (con tolerancia de clock skew);
    - `scope` debe contener el scope requerido.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str = "",
        public_key: str = "",
        kid: str = "",
        clock_skew_seconds: int = 60,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_url = jwks_url
        self._public_key = public_key
        self._kid = kid
        self._clock_skew = clock_skew_seconds
        self._jwks_cache: dict[str, object] | None = None
        self._jwks_fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _get_verification_key(self, kid: str | None) -> object | None:
        if self._public_key:
            return self._public_key
        if not self._jwks_url:
            return None
        jwks = await self._load_jwks()
        if not jwks:
            return None
        keys = jwks.get("keys", [])
        if kid:
            for key in keys:
                if key.get("kid") == kid:
                    return jwt.algorithms.RSAAlgorithm.from_jwk(key)
        if keys:
            return jwt.algorithms.RSAAlgorithm.from_jwk(keys[0])
        return None

    async def _load_jwks(self) -> dict | None:
        now = time.monotonic()
        if self._jwks_cache is not None and now - self._jwks_fetched_at < 3600:
            return self._jwks_cache
        async with self._lock:
            if self._jwks_cache is not None and now - self._jwks_fetched_at < 3600:
                return self._jwks_cache
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(self._jwks_url)
                    resp.raise_for_status()
                    self._jwks_cache = resp.json()
                    self._jwks_fetched_at = time.monotonic()
                    return self._jwks_cache
            except Exception:
                logger.warning("no se pudo obtener el JWKS de %s", self._jwks_url)
                return None

    async def validate(self, token: str, required_scope: str) -> dict:
        """Valida el token y devuelve sus claims si cumple el scope requerido.

        Lanza `ServiceAuthError` si el token no es un service token válido o no tiene scope.
        """
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.InvalidTokenError as exc:
            raise ServiceAuthError(401, "token inválido") from exc
        kid = unverified.get("kid") or self._kid
        try:
            key = await self._get_verification_key(kid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("clave de verificación no disponible: %s", exc)
            key = None
        if key is None:
            raise ServiceAuthError(503, "verification key unavailable")

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iss", "aud"]},
                leeway=self._clock_skew,
            )
        except jwt.ExpiredSignatureError as exc:
            raise ServiceAuthError(401, "token expirado") from exc
        except jwt.InvalidTokenError as exc:
            raise ServiceAuthError(401, "token inválido") from exc

        if claims.get("token_use") != "service":
            raise ServiceAuthError(403, "se requiere un service token")

        scopes = (claims.get("scope") or "").split()
        if required_scope not in scopes:
            raise ServiceAuthError(403, f"falta el scope {required_scope}")
        return claims


class ServiceAuthError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _required_scope(path: str, method: str) -> str:
    # Operaciones administrativas -> storage:admin (lectura y escritura del área admin).
    if path.startswith("/api/admin/"):
        return SCOPE_ADMIN
    # Escritura -> storage:write; lectura -> storage:read. Protect-all-by-default.
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return SCOPE_WRITE
    return SCOPE_READ


class ServiceAuthMiddleware(BaseHTTPMiddleware):
    """Protege todas las rutas por defecto con un service token.

    Exime `/api/v1/health` y `/metrics`. El resto exige un JWT de servicio válido con el
    scope según método/ruta (read/write/admin). Ningún endpoint futuro queda desprotegido.
    """

    def __init__(self, app, validator: ServiceTokenValidator) -> None:
        super().__init__(app)
        self._validator = validator

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        if path in EXEMPT_PATHS or path.startswith("/api/v1/health"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "se requiere service token"})

        token = auth_header[7:].strip()
        required = _required_scope(path, request.method)
        try:
            await self._validator.validate(token, required)
        except ServiceAuthError as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
        return await call_next(request)
