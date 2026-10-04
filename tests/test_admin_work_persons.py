"""Tests de la consulta admin Obra↔Persona: lista blanca de orden y filtros.

No tocan BD: `_order_by` y `_filters` son funciones puras que construyen SQL parametrizado.
"""

from __future__ import annotations

from api.routes.admin_work_persons import _filters, _order_by


def test_order_by_whitelist() -> None:
    assert _order_by("work", "desc") == "w.id DESC, w.id DESC, ro.id ASC"
    assert _order_by("person", "asc") == "p.persons_name ASC, w.id DESC, ro.id ASC"
    assert _order_by("origin", "ASC") == "w.works_origin ASC, w.id DESC, ro.id ASC"


def test_order_by_unknown_sort_falls_back_to_work_desc() -> None:
    # Cualquier valor del cliente fuera de la lista blanca cae a obra desc (nunca se interpola).
    assert _order_by("1; DROP TABLE works", "asc") == "w.id DESC, w.id DESC, ro.id ASC"


def test_filters_missing_ignores_person_and_role() -> None:
    where, params = _filters(None, "composer", True, "pid-1")
    assert where == "r.works_person_roles_id IS NULL"
    assert params == []


def test_filters_search_and_role() -> None:
    where, params = _filters("bach", "composer", False, None)
    assert "ro.role_name = %s" in where
    assert params == ["%bach%", "%bach%", "%bach%", "composer"]


def test_filters_by_person_id_is_trimmed() -> None:
    where, params = _filters(None, None, False, " pid-9 ")
    assert where == "r.works_person_roles_person_id = %s"
    assert params == ["pid-9"]
