from __future__ import annotations

from scripts.canonicalize_rism_persons import canonical_map


def _row(pid: str, gnd: str | None = None, viaf: str | None = None) -> dict:
    return {"rism_person_id": pid, "rism_gnd": gnd, "rism_viaf": viaf}


def test_shared_gnd_merges_to_lowest_id() -> None:
    mapping = canonical_map([_row("people/9", gnd="111"), _row("people/3", gnd="111")])
    assert mapping["people/9"] == "people/3"
    assert mapping["people/3"] == "people/3"


def test_shared_viaf_merges() -> None:
    mapping = canonical_map([_row("people/5", viaf="777"), _row("people/8", viaf="777")])
    assert mapping["people/5"] == mapping["people/8"]


def test_transitive_merge_through_shared_identifiers() -> None:
    mapping = canonical_map(
        [
            _row("people/1", gnd="a"),
            _row("people/2", gnd="a", viaf="x"),
            _row("people/3", viaf="x"),
        ]
    )
    assert len({mapping["people/1"], mapping["people/2"], mapping["people/3"]}) == 1


def test_without_shared_identifiers_stays_self() -> None:
    mapping = canonical_map([_row("people/1", gnd="a"), _row("people/2", gnd="b")])
    assert mapping["people/1"] == "people/1"
    assert mapping["people/2"] == "people/2"
