"""Resolutor de agrupación: Resource → Representation → Work.

Agrupaciones **inferidas** (no persistentes) a partir de la evidencia de los recursos. Emite:
grupos (obra), representaciones (por igualdad de ejes), reglas aplicadas, reglas de bloqueo o
revisión, y atributos comunes/divergentes.

Reglas generales (docsNew/diseño-resolutor-agrupacion.md §11):
1. La identidad de la obra es autoritativa sobre los ejes de realización.
2. Los recursos son la evidencia persistente; representación y obra son agrupaciones inferidas.
3. La identidad de compositor se determina por la **persona resuelta** (`composer_id` canónico) y
   sus variantes nominales como evidencia; el texto del nombre no decide por sí solo.
4. Título y catálogo son evidencia **complementaria**: el título genera candidatos, no identidad;
   el catálogo no convierte por sí solo la ausencia de compositor en identidad.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from domain.entities.composer_attribution import (
    STATE_AMBIGUOUS,
    STATE_UNCLASSIFIED,
    ComposerAttribution,
)
from domain.entities.resolution import (
    AMBIGUOUS_CANDIDATES,
    APPLIED,
    AXES_CONFIRM,
    AXES_CONFLICT_REVIEW,
    BLOCKED,
    CATALOGUE_CONFLICT,
    COMPOSER_MISMATCH,
    INSUFFICIENT_EVIDENCE,
    LEVEL_REPRESENTATION_WORK,
    LEVEL_RESOURCE_REPRESENTATION,
    ORIGIN_IDENTITY,
    ORIGIN_IDENTITY_MISSING,
    ORIGIN_METADATA,
    REVIEW,
    RISM_AMBIGUOUS,
    RISM_ATTRIBUTION,
    RISM_UNCLASSIFIED,
    WORK_IDENTITY,
    AxisValues,
    ResolutionResult,
    ResolutionRule,
    ResolvedGroup,
    ResolvedRepresentation,
    ResourceEvidence,
)
from domain.services.composer_names import normalize_composer_name


def representation_key(evidence: ResourceEvidence) -> str:
    """Identidad de origen (inventario): `(origin, origin_id)`. No es la representación final."""
    if evidence.origin_id:
        return f"{evidence.origin}:{evidence.origin_id}"
    return f"{evidence.origin}:res:{evidence.resource_id}"


def _text(value: str | None) -> str:
    return normalize_composer_name(value)


def _axes_signature(axes: AxisValues) -> tuple[object, ...]:
    return (
        tuple(sorted(axes.voicing)),
        tuple(sorted(axes.ensembles)),
        tuple(sorted(axes.instruments)),
        tuple(sorted(axes.languages)),
        (axes.key or "").strip().lower(),
    )


def _signature_key(axes: AxisValues) -> str:
    sig = _axes_signature(axes)
    return "|".join(",".join(part) if isinstance(part, tuple) else str(part) for part in sig)


def _rule(
    rule: str, level: str, outcome: str, evidence: dict[str, object], explanation: str
) -> ResolutionRule:
    return ResolutionRule(
        rule=rule, level=level, outcome=outcome, evidence=evidence, explanation=explanation
    )


def _attributes(
    members: list[ResourceEvidence],
) -> tuple[dict[str, object], dict[str, list[object]]]:
    values: dict[str, list[object]] = {
        "voicing": [m.axes.voicing for m in members],
        "ensembles": [m.axes.ensembles for m in members],
        "instruments": [m.axes.instruments for m in members],
        "languages": [m.axes.languages for m in members],
        "key": [(m.axes.key or "") for m in members],
        "license": [m.license for m in members],
        "editors": [m.editors for m in members],
    }
    common: dict[str, object] = {}
    divergent: dict[str, list[object]] = {}
    for name, seq in values.items():
        unique = list(dict.fromkeys(seq))
        if len(unique) == 1:
            common[name] = unique[0]
        else:
            divergent[name] = unique
    return common, divergent


def _representation(members: list[ResourceEvidence], work_key: str, index: int) -> ResolvedRepresentation:
    common, divergent = _attributes(members)
    first = members[0]
    return ResolvedRepresentation(
        key=f"{work_key}::rep{index}:{_signature_key(first.axes)}",
        source_keys=tuple(sorted({representation_key(m) for m in members})),
        resource_ids=tuple(sorted(m.resource_id for m in members)),
        attributes_common=common,
        attributes_divergent=divergent,
    )


def _work_group(
    work_key: str,
    evidences: list[ResourceEvidence],
    applied: list[ResolutionRule],
) -> ResolvedGroup:
    by_signature: dict[str, list[ResourceEvidence]] = defaultdict(list)
    for evidence in evidences:
        by_signature[_signature_key(evidence.axes)].append(evidence)
    representations: list[ResolvedRepresentation] = []
    for index, signature in enumerate(sorted(by_signature)):
        members = by_signature[signature]
        if len(members) > 1:
            applied.append(
                _rule(
                    AXES_CONFIRM,
                    LEVEL_RESOURCE_REPRESENTATION,
                    APPLIED,
                    {"work": work_key, "axes": members[0].axes.as_dict()},
                    "ejes musicales iguales: mismos recursos forman una representación",
                )
            )
        representations.append(_representation(members, work_key, index))
    common, divergent = _attributes(evidences)
    first = evidences[0]
    return ResolvedGroup(
        key=work_key,
        work_ids=tuple(sorted({m.work_id for m in evidences})),
        representations=representations,
        resource_ids=tuple(sorted(m.resource_id for m in evidences)),
        identity={
            "title": _text(first.title),
            "composer": _text(first.composer),
            "catalogue": _text(first.catalogue),
        },
        attributes_common=common,
        attributes_divergent=divergent,
    )


@dataclass(frozen=True)
class _Unit:
    """Unidad de origen (representación de inventario) con la identidad de su obra."""

    key: str
    members: list[ResourceEvidence]
    title: str
    composer: str | None
    composer_id: str | None
    aliases: frozenset[str]
    catalogue: str | None
    attribution: ComposerAttribution | None = None

    @property
    def effective_person_id(self) -> str | None:
        """Identidad de compositor: la nuestra, o la de una atribución RISM usable."""
        if self.composer_id:
            return self.composer_id
        if self.attribution is not None and self.attribution.usable_for_identity:
            return self.attribution.person_id
        return None

    @property
    def has_composer(self) -> bool:
        if not self.effective_person_id:
            return False
        if self.composer_id:
            return bool(_text(self.composer))
        return bool(self.attribution and self.attribution.person_name)

    @property
    def composer_label(self) -> str:
        return self.effective_person_id or "?"

    @property
    def attribution_used(self) -> bool:
        return bool(
            not self.composer_id
            and self.attribution is not None
            and self.attribution.usable_for_identity
        )

    def catalogues_ok(self, other: _Unit) -> bool:
        mine, theirs = _text(self.catalogue), _text(other.catalogue)
        return not (mine and theirs and mine != theirs)


def _same_person(a: _Unit, b: _Unit) -> bool:
    """Persona canónica o variante nominal demostrada por alias (nunca solo el texto)."""
    ea, eb = a.effective_person_id, b.effective_person_id
    if not ea or not eb:
        return False
    if ea == eb:
        return True
    if not a.composer_id or not b.composer_id:
        return False  # una identidad viene de atribución: solo vale la igualdad exacta
    na, nb = _text(a.composer), _text(b.composer)
    left = {x for x in a.aliases if x and x != na}
    right = {x for x in b.aliases if x and x != nb}
    return (bool(na) and na in right) or (bool(nb) and nb in left) or bool(left & right)


class _Find:
    def __init__(self, keys: list[str]) -> None:
        self._parent = {k: k for k in keys}

    def find(self, x: str) -> str:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


def _unit(
    key: str, members: list[ResourceEvidence], attribution: ComposerAttribution | None
) -> _Unit:
    first = members[0]
    return _Unit(
        key=key,
        members=members,
        title=first.title or "",
        composer=first.composer,
        composer_id=first.composer_id,
        aliases=frozenset(first.composer_aliases),
        catalogue=first.catalogue,
        attribution=attribution,
    )


def resolve(
    evidences: list[ResourceEvidence],
    attributions: dict[int, ComposerAttribution] | None = None,
) -> ResolutionResult:
    if not evidences:
        return ResolutionResult(groups=[], applied=[], blocked=[], review=[])

    applied: list[ResolutionRule] = []
    blocked: list[ResolutionRule] = []
    review: list[ResolutionRule] = []

    # --- Resolución 1: Resource → unidad de origen (inventario) + reglas de identidad/ejes ---
    raw_units: dict[str, list[ResourceEvidence]] = defaultdict(list)
    for evidence in evidences:
        raw_units[representation_key(evidence)].append(evidence)

    for source_key in sorted(raw_units):
        members = raw_units[source_key]
        first = members[0]
        if first.origin_id:
            applied.append(
                _rule(
                    ORIGIN_IDENTITY,
                    LEVEL_RESOURCE_REPRESENTATION,
                    APPLIED,
                    {"origin": first.origin, "origin_id": first.origin_id},
                    f"identidad de origen {first.origin}:{first.origin_id}",
                )
            )
        else:
            review.append(
                _rule(
                    ORIGIN_IDENTITY_MISSING,
                    LEVEL_RESOURCE_REPRESENTATION,
                    REVIEW,
                    {"origin": first.origin, "resource_id": first.resource_id},
                    "sin origin_id: no se puede agrupar por identidad de origen",
                )
            )
        editors = sorted({e for m in members for e in m.editors})
        licenses = sorted({m.license for m in members if m.license})
        applied.append(
            _rule(
                ORIGIN_METADATA,
                LEVEL_RESOURCE_REPRESENTATION,
                APPLIED,
                {"editors": editors, "licenses": licenses},
                "editor/licencia coincidentes aportan evidencia adicional; "
                "sus diferencias no bloquean la agrupación",
            )
        )
        signatures = {_axes_signature(m.axes) for m in members}
        if len(signatures) > 1:
            review.append(
                _rule(
                    AXES_CONFLICT_REVIEW,
                    LEVEL_RESOURCE_REPRESENTATION,
                    REVIEW,
                    {
                        "origin_id": first.origin_id,
                        "signatures": [_axes_signature(m.axes) for m in members],
                    },
                    "mismo origen pero ejes incompatibles: posibles datos contradictorios; "
                    "los recursos se reparten en representaciones distintas",
                )
            )

    units = [
        _unit(
            key,
            raw_units[key],
            (attributions or {}).get(raw_units[key][0].work_id),
        )
        for key in sorted(raw_units)
    ]

    # --- Resolución 2: Representation → Work (título = candidatos; compositor = identidad) ---
    by_title: dict[str, list[_Unit]] = defaultdict(list)
    for unit in units:
        by_title[_text(unit.title)].append(unit)

    groups: list[ResolvedGroup] = []
    for title_norm in sorted(by_title):
        bucket = by_title[title_norm]
        if not title_norm:
            for unit in bucket:
                blocked.append(
                    _rule(
                        INSUFFICIENT_EVIDENCE,
                        LEVEL_REPRESENTATION_WORK,
                        BLOCKED,
                        {"title": None, "representation": unit.key},
                        "sin título normalizable: no se puede establecer candidatura de obra",
                    )
                )
                groups.append(_work_group(f"work:unknown:{unit.key}", unit.members, applied))
            continue

        # union-find por identidad de compositor (título ya empareja)
        find_set = _Find([unit.key for unit in bucket])

        composer_mismatch: set[tuple[str, str]] = set()
        catalogue_conflict: set[tuple[str, str]] = set()
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                if not a.catalogues_ok(b):
                    catalogue_conflict.add(tuple(sorted([a.key, b.key])))
                    continue
                if _same_person(a, b):
                    find_set.union(a.key, b.key)
                elif a.has_composer and b.has_composer:
                    composer_mismatch.add((_text(a.composer) or "?", _text(b.composer) or "?"))

        for a, b in sorted(catalogue_conflict):
            blocked.append(
                _rule(
                    CATALOGUE_CONFLICT,
                    LEVEL_REPRESENTATION_WORK,
                    BLOCKED,
                    {"title": title_norm, "representations": [a, b]},
                    "mismo título pero catálogos distintos: no se fuerzan a una obra",
                )
            )
        for ca, cb in sorted(composer_mismatch):
            blocked.append(
                _rule(
                    COMPOSER_MISMATCH,
                    LEVEL_REPRESENTATION_WORK,
                    BLOCKED,
                    {"title": title_norm, "composers": sorted({ca, cb})},
                    "mismo título pero compositores distintos: no se unen en la misma obra",
                )
            )
        for unit in bucket:
            if not unit.has_composer:
                blocked.append(
                    _rule(
                        INSUFFICIENT_EVIDENCE,
                        LEVEL_REPRESENTATION_WORK,
                        BLOCKED,
                        {"title": title_norm, "representation": unit.key},
                        "sin compositor resuelto: candidato sin identidad de obra demostrada",
                    )
                )
            attribution = unit.attribution
            if attribution is not None and attribution.state == STATE_AMBIGUOUS:
                review.append(
                    _rule(
                        RISM_AMBIGUOUS,
                        LEVEL_REPRESENTATION_WORK,
                        REVIEW,
                        {
                            "title": title_norm,
                            "representation": unit.key,
                            "source": attribution.source,
                            "reliability": attribution.reliability,
                            "person_id": attribution.person_id,
                        },
                        "atribución externa ambigua: requiere revisión, no resuelve identidad",
                    )
                )
            elif unit.attribution_used and attribution is not None:
                applied.append(
                    _rule(
                        RISM_ATTRIBUTION,
                        LEVEL_REPRESENTATION_WORK,
                        APPLIED,
                        {
                            "title": title_norm,
                            "representation": unit.key,
                            "source": attribution.source,
                            "state": attribution.state,
                            "reliability": attribution.reliability,
                            "person_id": attribution.person_id,
                            "via": attribution.via,
                        },
                        f"atribución externa ({attribution.source}, {attribution.state}) "
                        "aporta identidad de compositor",
                    )
                )
            elif attribution is not None and attribution.state == STATE_UNCLASSIFIED:
                review.append(
                    _rule(
                        RISM_UNCLASSIFIED,
                        LEVEL_REPRESENTATION_WORK,
                        REVIEW,
                        {
                            "title": title_norm,
                            "representation": unit.key,
                            "source": attribution.source,
                            "person_id": attribution.person_id,
                            "via": attribution.via,
                        },
                        "atribución externa sin fiabilidad ($j): evidencia débil, no resuelve",
                    )
                )

        components: dict[str, list[_Unit]] = defaultdict(list)
        for unit in bucket:
            components[find_set.find(unit.key)].append(unit)

        for root in sorted(components):
            component = components[root]
            if len(component) > 1:
                applied.append(
                    _rule(
                        WORK_IDENTITY,
                        LEVEL_REPRESENTATION_WORK,
                        APPLIED,
                        {
                            "title": title_norm,
                            "composer_id": component[0].effective_person_id,
                            "representations": sorted(u.key for u in component),
                        },
                        "misma persona (identidad canónica) bajo el mismo título: misma obra inferida",
                    )
                )
            composer_label = component[0].composer_label
            catalogue_norm = _text(component[0].catalogue)
            work_key = f"work:{title_norm}|{composer_label}|{catalogue_norm}"
            members = [m for unit in component for m in unit.members]
            groups.append(_work_group(work_key, members, applied))

    # Ambiguos: título con más de un catálogo y unidades sin catálogo
    for title_norm in sorted(by_title):
        bucket = by_title[title_norm]
        catalogues = sorted({_text(u.catalogue) for u in bucket if _text(u.catalogue)})
        if len(catalogues) > 1:
            for unit in bucket:
                if not _text(unit.catalogue):
                    review.append(
                        _rule(
                            AMBIGUOUS_CANDIDATES,
                            LEVEL_REPRESENTATION_WORK,
                            REVIEW,
                            {"title": title_norm, "catalogues": catalogues,
                             "representation": unit.key},
                            "sin catálogo pero con catálogos en conflicto: candidato ambiguo",
                        )
                    )

    groups.sort(key=lambda g: g.key)
    return ResolutionResult(
        groups=groups,
        applied=_dedupe(applied),
        blocked=_dedupe(blocked),
        review=_dedupe(review),
    )


def _dedupe(rules: list[ResolutionRule]) -> list[ResolutionRule]:
    seen: set[str] = set()
    out: list[ResolutionRule] = []
    for rule in rules:
        key = json.dumps(
            [rule.rule, rule.level, rule.outcome, rule.evidence], sort_keys=True, default=str
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(rule)
    out.sort(key=lambda r: (r.rule, r.level, r.outcome))
    return out
