"""Tests del motor de revisión: guardarraíles, idempotencia y previews."""

from __future__ import annotations

import json

import pytest
from application.use_cases.review_engine import (
    DecisionExistenteDistinta,
    PreviewNoValidado,
    ReviewEngine,
)


class _FakeRepo:
    def __init__(self) -> None:
        self.unidades: list[dict] = []
        self.conflictos_filas: list[dict] = []
        self.existentes: dict[str, str] = {}
        self.insertadas: list[dict] = []

    async def unidades_tramo(self, tramo: str, role_key: str | None, limite: int) -> list[dict]:
        return self.unidades[:limite]

    async def conflictos(self) -> list[dict]:
        return self.conflictos_filas

    async def decisiones_existentes(self, claves: list[str]) -> dict[str, str]:
        return {c: self.existentes[c] for c in claves if c in self.existentes}

    async def insertar_decisiones(self, filas: list[dict]) -> int:
        self.insertadas.extend(filas)
        return len(filas)


def _unidad(item_key: str, person_key: str, obras: int = 3, estados: str = "resolved") -> dict:
    return {
        "item_key": item_key, "person_key": person_key, "role_key": "composer", "obras": obras,
        "roles": "composer", "estados": estados, "candidatos_json": "[]",
        "contexto_json": json.dumps({"nombres_vistos": ["j s bach"], "colision_de_clave": False}),
    }


async def test_preview_rechaza_decision_invalida() -> None:
    engine = ReviewEngine(_FakeRepo())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await engine.preview_tramo("A", "inventada", batch="A-1")


async def test_materializar_exige_hash_del_preview() -> None:
    repo = _FakeRepo()
    repo.unidades = [_unidad("identity_cluster||viaf:1|", "viaf:1")]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]
    preview = await engine.preview_tramo("A", "accept", batch="A-0001")

    with pytest.raises(PreviewNoValidado):
        await engine.materializar(preview, confirm="hash-incorrecto", decided_by="admin", apply=True)
    assert repo.insertadas == []


async def test_materializar_una_decision_por_unidad() -> None:
    repo = _FakeRepo()
    repo.unidades = [_unidad(f"identity_cluster||viaf:{i}|", f"viaf:{i}") for i in range(3)]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]
    preview = await engine.preview_tramo("A", "accept", batch="A-0001")

    resultado = await engine.materializar(preview, confirm=preview.hash(), decided_by="admin", apply=True)

    assert resultado["nuevas"] == 3 and resultado["insertadas"] == 3
    assert all(f["decision"] == "accept" and f["decision_type"] == "identity" for f in repo.insertadas)
    evidence = json.loads(repo.insertadas[0]["evidence_json"])
    assert evidence["decision_mode"] == "bulk:A" and evidence["preview_hash"] == preview.hash()


async def test_no_duplica_ni_altera_decisiones_existentes() -> None:
    repo = _FakeRepo()
    repo.unidades = [_unidad("identity_cluster||viaf:1|", "viaf:1")]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]
    preview = await engine.preview_tramo("A", "accept", batch="A-0001")
    clave = "identity||viaf:1|composer"
    repo.existentes[clave] = "accept"

    resultado = await engine.materializar(preview, confirm=preview.hash(), decided_by="admin", apply=True)

    assert resultado["ya_existentes"] == 1 and resultado["insertadas"] == 0
    assert repo.insertadas == []


async def test_una_decision_distinta_no_se_altera() -> None:
    repo = _FakeRepo()
    repo.unidades = [_unidad("identity_cluster||viaf:1|", "viaf:1")]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]
    preview = await engine.preview_tramo("A", "accept", batch="A-0001")
    repo.existentes["identity||viaf:1|composer"] = "not_a_person"

    with pytest.raises(DecisionExistenteDistinta):
        await engine.materializar(preview, confirm=preview.hash(), decided_by="admin", apply=True)
    assert repo.insertadas == []


async def test_conflictos_no_admiten_lote_y_se_listan() -> None:
    repo = _FakeRepo()
    repo.conflictos_filas = [{"work_key": "CPDL:1", "person_key": "viaf:1", "role_key": "composer",
                        "attribution_status": "traditional", "personas": [], "obras": 1}]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    preview = await engine.preview_conflictos()

    assert preview.unidad == "conflict" and preview.resumen["obras"] == 1
    assert preview.decision == ""


async def test_muestra_y_excepciones_del_preview() -> None:
    repo = _FakeRepo()
    repo.unidades = [
        _unidad("identity_cluster||viaf:1|", "viaf:1"),
        _unidad("identity_cluster||name:x|", "name:x", estados="review_target_contaminated"),
    ]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]
    preview = await engine.preview_tramo("B", "accept", batch="B-0001")

    assert preview.resumen["unidades"] == 2
    assert len(preview.excepciones) == 1
    assert preview.excepciones[0]["person_key"] == "name:x"
