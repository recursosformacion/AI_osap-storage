"""Deriva el contexto de formación (ensemble) de una representación (Bloque 3).

Autoridad:
    representation.representations_ensemble_code  ->  ensembles.ensembles_code (id_canonico)
                                                       ->  ensemble_voices
`voice_signature` es un dato **derivado** (firma de frecuencias, p. ej. `S2A2T2B2`) para
búsqueda; nunca es fuente de verdad.

`ensemble_code` se obtiene aplicando `canonical_ensemble()` a los campos de formación de la
representación (p. ej. el `voicing` del proveedor), no copiando un código antiguo. Si los
términos son ambiguos (varias formaciones distintas) o no forman voces, se devuelve `None`.
"""

from __future__ import annotations

from collections.abc import Iterable

from domain.services.ensemble_canonical import VOICE_ORDER, canonical_ensemble

_NON_FORMATION_KINDS = frozenset({"INVALID", "UNKNOWN", "DESCRIPTOR"})


def voice_signature(ensemble_code: str | None) -> str | None:
    """Firma de frecuencias del id canónico (`S2A2T2B2`), o `None` si no es una formación."""
    if not ensemble_code:
        return None
    info = canonical_ensemble(ensemble_code)
    if info.kind != "VOICES" or not info.voice_counts:
        return None
    return "".join(
        f"{v}{info.voice_counts[v]}" for v in VOICE_ORDER if info.voice_counts.get(v, 0) > 0
    )


def derive_from_terms(terms: Iterable[str]) -> tuple[str | None, str | None]:
    """Canonicaliza los términos de formación y devuelve `(ensemble_code, voice_signature)`.

    Solo resuelve si **todos** los términos útiles coinciden en un único id canónico; ante
    ambigüedad (varias formaciones) o ausencia de voces devuelve `(None, None)`.
    """
    codes: set[str] = set()
    for raw in terms:
        if raw is None or not str(raw).strip():
            continue
        info = canonical_ensemble(str(raw))
        if info.kind in _NON_FORMATION_KINDS:
            continue
        codes.add(info.id_canonico)
    if len(codes) == 1:
        code = next(iter(codes))
        return code, voice_signature(code)
    return None, None
