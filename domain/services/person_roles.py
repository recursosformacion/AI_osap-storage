"""Roles de persona: clave de API (inglesa) ↔ id de `roles` en osap-storage.

La API pública/admin acepta los roles por clave (`composer`, `arranger`, `performer`,
`editor`…), que es estable para las aplicaciones; en la BBDD el rol es un id numérico
(`roles.id`). Tabla sembrada en la migración (roles 1..15).

`role_name` en la tabla está en español ("Compositor/a"); aquí se mantiene la traducción.
"""

from __future__ import annotations

from collections.abc import Iterable

ROLE_IDS: dict[str, int] = {
    "composer": 1,
    "librettist": 2,
    "arranger": 3,
    "orchestrator": 4,
    "transcriber": 5,
    "editor": 6,
    "completer": 7,
    "conductor": 8,
    "choir_conductor": 9,
    "performer": 10,
    "kapellmeister": 11,
    "vocal_coach": 12,
    "dedicatee": 13,
    "patron": 14,
    "inspiration": 15,
}

ROLE_KEYS: dict[int, str] = {role_id: key for key, role_id in ROLE_IDS.items()}

DEFAULT_ROLE = "composer"


class UnknownRoleError(ValueError):
    """Rol pedido que no existe en el catálogo."""


def role_key(role_id: int) -> str | None:
    return ROLE_KEYS.get(int(role_id))


def parse_role_keys(value: str | Iterable[str] | None, *, default: str = DEFAULT_ROLE) -> tuple[str, ...]:
    """`composer,arranger` → claves válidas (sin duplicados). Vacío → `(default,)`.

    Lanza `UnknownRoleError` con las claves desconocidas (la API responde 400).
    """
    if value is None:
        return (default,)
    raw = value.split(",") if isinstance(value, str) else list(value)
    keys: list[str] = []
    unknown: list[str] = []
    for item in raw:
        key = str(item).strip().lower()
        if not key:
            continue
        if key not in ROLE_IDS:
            unknown.append(key)
            continue
        if key not in keys:
            keys.append(key)
    if unknown:
        raise UnknownRoleError(", ".join(sorted(set(unknown))))
    return tuple(keys) if keys else (default,)


def role_ids_for(keys: Iterable[str], *, default: str = DEFAULT_ROLE) -> tuple[int, ...]:
    """Claves → ids de `roles` (si no hay ninguna válida, el rol por defecto)."""
    ids = tuple(ROLE_IDS[key] for key in keys if key in ROLE_IDS)
    return ids or (ROLE_IDS[default],)
