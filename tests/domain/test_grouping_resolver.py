from __future__ import annotations

from application.use_cases.resolution import _best_attribution
from domain.entities.composer_attribution import ComposerAttribution
from domain.entities.resolution import AxisValues, ResolutionResult, ResourceEvidence
from domain.services.grouping_resolver import resolve


def _attr(person_id: str | None, state: str, reliability: str | None = None) -> ComposerAttribution:
    return ComposerAttribution(
        person_id=person_id, person_name="X" if person_id else None,
        state=state, reliability=reliability,
    )


def _ev(
    resource_id: int,
    *,
    origin: str = "pdmx",
    origin_id: str | None = "QmA",
    work_id: int = 1,
    title: str | None = "T",
    composer: str | None = "C",
    composer_id: str | None = "",
    aliases: tuple[str, ...] = (),
    catalogue: str | None = None,
    license_: str = "pd",
    editors: tuple[str, ...] = (),
    axes: AxisValues | None = None,
) -> ResourceEvidence:
    if composer_id == "":  # por defecto, la identidad va ligada al nombre
        composer_id = composer
    return ResourceEvidence(
        resource_id=resource_id,
        resource_type="MXL",
        representation_id=resource_id,
        origin=origin,
        origin_id=origin_id,
        license=license_,
        editors=editors,
        work_id=work_id,
        title=title,
        catalogue=catalogue,
        composer=composer,
        composer_id=composer_id,
        composer_aliases=aliases,
        axes=axes or AxisValues(),
    )


def _has(rules, name: str) -> bool:
    return any(r.rule == name for r in rules)


def test_same_origin_identity_confirms_group() -> None:
    result: ResolutionResult = resolve(
        [
            _ev(1, origin_id="cpdl:1", axes=AxisValues(voicing=("SATB",))),
            _ev(2, origin_id="cpdl:1", axes=AxisValues(voicing=("SATB",))),
        ]
    )
    assert len(result.groups) == 1
    assert result.groups[0].resource_ids == (1, 2)
    assert len(result.groups[0].representations) == 1
    assert _has(result.applied, "origin_identity")
    assert _has(result.applied, "axes_confirm")


def test_conflicting_axes_with_same_origin_requires_review() -> None:
    result = resolve(
        [
            _ev(1, origin_id="cpdl:1", axes=AxisValues(voicing=("SATB",))),
            _ev(2, origin_id="cpdl:1", axes=AxisValues(voicing=("TTBB",))),
        ]
    )
    assert _has(result.review, "axes_conflict_review")
    assert len(result.groups) == 1
    # los ejes distintos reparten los recursos en dos representaciones
    assert len(result.groups[0].representations) == 2
    assert "voicing" in result.groups[0].attributes_divergent


def test_work_identity_merges_across_origins() -> None:
    result = resolve(
        [
            _ev(1, origin="cpdl", origin_id="10:20", work_id=10, catalogue="BWV 1"),
            _ev(2, origin="pdmx", origin_id="QmX", work_id=20, catalogue="BWV 1"),
        ]
    )
    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.work_ids == (10, 20)
    assert len(group.representations) == 1
    assert len(group.representations[0].source_keys) == 2
    assert _has(result.applied, "work_identity")


def test_catalogue_conflict_blocks_merge() -> None:
    result = resolve(
        [
            _ev(1, origin="cpdl", origin_id="10:20", work_id=10, catalogue="BWV 1"),
            _ev(2, origin="pdmx", origin_id="QmX", work_id=20, catalogue="BWV 2"),
        ]
    )
    assert len(result.groups) == 2
    assert _has(result.blocked, "catalogue_conflict")


def test_composer_mismatch_blocks_merge() -> None:
    result = resolve(
        [
            _ev(1, composer="Ana", origin_id="a:1", work_id=1),
            _ev(2, composer="Beto", origin_id="b:1", work_id=2),
        ]
    )
    assert len(result.groups) == 2
    assert _has(result.blocked, "composer_mismatch")


def test_insufficient_evidence_without_composer() -> None:
    result = resolve([_ev(1, composer=None, origin_id="a:1", work_id=1)])
    assert _has(result.blocked, "insufficient_evidence")
    assert result.groups and result.groups[0].resource_ids == (1,)


def test_encoding_resources_share_representation() -> None:
    result = resolve(
        [
            _ev(1, origin_id="cpdl:1", axes=AxisValues(voicing=("SATB",))),
            _ev(2, origin_id="cpdl:1", axes=AxisValues(voicing=("SATB",))),
            _ev(3, origin_id="cpdl:1", axes=AxisValues(voicing=("SATB",))),
        ]
    )
    assert len(result.groups) == 1
    assert len(result.groups[0].resource_ids) == 3
    assert len(result.groups[0].representations) == 1
    assert len(result.groups[0].representations[0].source_keys) == 1


def test_metadata_differences_do_not_block() -> None:
    result = resolve(
        [
            _ev(1, origin_id="cpdl:1", license_="CPDL", editors=("E1",)),
            _ev(2, origin_id="cpdl:1", license_="Personal", editors=("E2",)),
        ]
    )
    assert len(result.groups) == 1
    assert _has(result.applied, "origin_metadata")
    assert not result.blocked
    assert "license" in result.groups[0].attributes_divergent


def test_composer_identity_uses_person_not_name() -> None:
    # mismo nombre, personas distintas y sin alias: no se unen
    result = resolve(
        [
            _ev(1, origin_id="a:1", work_id=1, composer="C", composer_id="p1"),
            _ev(2, origin_id="b:1", work_id=2, composer="C", composer_id="p2"),
        ]
    )
    assert len(result.groups) == 2
    assert _has(result.blocked, "composer_mismatch")


def test_composer_alias_variant_merges() -> None:
    # personas distintas, pero la variante nominal está demostrada por alias
    result = resolve(
        [
            _ev(1, origin_id="a:1", work_id=1, composer="J S Bach", composer_id="p1"),
            _ev(2, origin_id="b:1", work_id=2, composer="Johann Sebastian Bach",
                composer_id="p2", aliases=("j s bach",)),
        ]
    )
    assert len(result.groups) == 1
    assert _has(result.applied, "work_identity")


def test_rism_resolved_attribution_supplies_identity() -> None:
    without = _ev(1, origin_id="a:1", work_id=1, composer=None, composer_id=None)
    with_composer = _ev(2, origin_id="b:1", work_id=2, composer="C", composer_id="p1")
    result = resolve([without, with_composer], {1: _attr("p1", "resolved", "Verified")})
    assert len(result.groups) == 1
    assert _has(result.applied, "rism_attribution")
    assert _has(result.applied, "work_identity")


def test_rism_inferred_attribution_supplies_identity() -> None:
    without = _ev(1, origin_id="a:1", work_id=1, composer=None, composer_id=None)
    with_composer = _ev(2, origin_id="b:1", work_id=2, composer="C", composer_id="p1")
    result = resolve([without, with_composer], {1: _attr("p1", "inferred", "Ascertained")})
    assert len(result.groups) == 1
    assert _has(result.applied, "rism_attribution")


def test_rism_ambiguous_attribution_requires_review() -> None:
    without = _ev(1, origin_id="a:1", work_id=1, composer=None, composer_id=None)
    with_composer = _ev(2, origin_id="b:1", work_id=2, composer="C", composer_id="p1")
    result = resolve([without, with_composer], {1: _attr(None, "ambiguous", "Conjectural")})
    assert _has(result.review, "rism_ambiguous")
    assert len(result.groups) == 2


def test_rism_unclassified_is_not_used() -> None:
    without = _ev(1, origin_id="a:1", work_id=1, composer=None, composer_id=None)
    result = resolve([without], {1: _attr("p1", "unclassified")})
    assert _has(result.blocked, "insufficient_evidence")
    assert not _has(result.applied, "rism_attribution")
    # pero no se pierde: queda registrada como evidencia débil para revisión
    assert _has(result.review, "rism_unclassified")


def test_best_attribution_multiple_resolved_is_ambiguous() -> None:
    best = _best_attribution([_attr("p1", "resolved"), _attr("p2", "resolved")])
    assert best is not None and best.state == "ambiguous" and best.person_id is None


def test_best_attribution_prefers_resolved() -> None:
    best = _best_attribution([_attr("p1", "inferred"), _attr("p2", "resolved")])
    assert best is not None and best.person_id == "p2"
