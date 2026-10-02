"""Tests del motor de revisión: guardarraíles, idempotencia y previews."""

from __future__ import annotations

import json

import pytest
from application.use_cases.review_engine import (
    DecisionExistenteDistinta,
    PreviewNoValidado,
    ReviewEngine,
)
from infrastructure.repositories.sql_review_repository import condiciones_tramo


class _FakeRepo:
    def __init__(self) -> None:
        self.unidades: list[dict] = []
        self.conflictos_filas: list[dict] = []
        self.existentes: dict[str, str] = {}
        self.insertadas: list[dict] = []

    async def unidades_tramo(self, tramo: str, role_key: str | None, limite: int) -> list[dict]:
        return self.unidades[:limite]

    async def cluster_identidad(self, person_key: str, role_key: str | None = None) -> dict | None:
        for unidad in self.unidades:
            if unidad["person_key"] == person_key and (role_key is None or unidad.get("role_key") == role_key):
                return unidad
        return None

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


async def test_decision_individual_de_conflicto() -> None:
    repo = _FakeRepo()
    repo.conflictos_filas = [{"item_key": "conflict|CPDL:1|", "work_key": "CPDL:1", "person_key": "viaf:1",
                              "role_key": "composer", "attribution_status": "traditional", "personas": [],
                              "obras": 1}]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    resultado = await engine.decidir_conflicto("CPDL:1", "persona_gana", decided_by="admin", apply=True)

    assert resultado["insertadas"] == 1
    assert repo.insertadas[0]["decision_type"] == "conflict"
    assert repo.insertadas[0]["decision"] == "persona_gana"


async def test_conflicto_valida_decision_y_existencia() -> None:
    repo = _FakeRepo()
    repo.conflictos_filas = [{"item_key": "conflict|CPDL:1|", "work_key": "CPDL:1", "person_key": "viaf:1",
                              "role_key": "composer", "attribution_status": "traditional", "personas": [], "obras": 1}]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        await engine.decidir_conflicto("CPDL:1", "inventada", decided_by="admin")
    with pytest.raises(LookupError):
        await engine.decidir_conflicto("CPDL:999", "persona_gana", decided_by="admin")
    repo.existentes["conflict|CPDL:1||"] = "atribucion_gana"
    with pytest.raises(DecisionExistenteDistinta):
        await engine.decidir_conflicto("CPDL:1", "persona_gana", decided_by="admin")


class _FakeRepoHistorial(_FakeRepo):
    def __init__(self) -> None:
        super().__init__()
        self.historial_filas: list[dict] = []

    async def insertar_historial(self, filas: list[dict]) -> int:
        self.historial_filas.extend(filas)
        return len(filas)

    async def actualizar_decision(self, decision_key: str, decision: str, notes: str | None) -> int:
        if decision_key not in self.existentes:
            return 0
        self.existentes[decision_key] = decision
        return 1


async def test_conflict_guarda_nota_y_evidencia() -> None:
    repo = _FakeRepo()
    repo.conflictos_filas = [{"item_key": "conflict|CPDL:1|", "work_key": "CPDL:1", "person_key": "viaf:1",
                              "role_key": "composer", "attribution_status": "traditional", "personas": [], "obras": 1}]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    await engine.decidir_conflicto(
        "CPDL:1", "atribucion_gana", decided_by="mgarcia",
        note="tradicional galesa", evidence="consulta web del revisor", apply=True,
    )

    evidencia = json.loads(repo.insertadas[0]["evidence_json"])
    assert evidencia["researcher_note"] == "consulta web del revisor"
    assert repo.insertadas[0]["notes"] == "tradicional galesa"


async def test_correccion_conserva_original_y_actualiza_vigente() -> None:
    repo = _FakeRepoHistorial()
    repo.existentes["conflict|CPDL:1||"] = "persona_gana"
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    resultado = await engine.corregir_decision(
        "conflict|CPDL:1||", "atribucion_gana", decided_by="mgarcia",
        reason="la fuente documenta melodia tradicional", apply=True,
    )

    assert resultado["estado"] == "corregida" and resultado["actualizada"] == 1
    assert repo.existentes["conflict|CPDL:1||"] == "atribucion_gana"       # vigente nueva
    assert repo.historial_filas[0]["previous_decision"] == "persona_gana"   # original conservada
    assert repo.historial_filas[0]["new_decision"] == "atribucion_gana"


async def test_segunda_correccion_deja_historial_completo() -> None:
    repo = _FakeRepoHistorial()
    repo.existentes["attribution|CPDL:1||"] = "traditional"
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    await engine.corregir_decision("attribution|CPDL:1||", "anonymous", decided_by="a", reason="r1", apply=True)
    await engine.corregir_decision("attribution|CPDL:1||", "traditional", decided_by="b", reason="r2", apply=True)

    assert [(f["previous_decision"], f["new_decision"]) for f in repo.historial_filas] == [
        ("traditional", "anonymous"), ("anonymous", "traditional"),
    ]
    assert repo.existentes["attribution|CPDL:1||"] == "traditional"


async def test_correccion_invalida_no_cambia_nada() -> None:
    repo = _FakeRepoHistorial()
    repo.existentes["conflict|CPDL:1||"] = "persona_gana"
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        await engine.corregir_decision("conflict|CPDL:1||", "atribucion_gana", decided_by="a", reason="", apply=True)
    with pytest.raises(LookupError):
        await engine.corregir_decision("conflict|CPDL:999||", "persona_gana", decided_by="a", reason="r", apply=True)
    assert repo.historial_filas == []
    assert repo.existentes["conflict|CPDL:1||"] == "persona_gana"


async def test_correccion_repetida_no_duplica() -> None:
    repo = _FakeRepoHistorial()
    repo.existentes["conflict|CPDL:1||"] = "atribucion_gana"
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    resultado = await engine.corregir_decision(
        "conflict|CPDL:1||", "atribucion_gana", decided_by="a", reason="r", apply=True
    )

    assert resultado["estado"] == "sin_cambios" and repo.historial_filas == []


async def test_correccion_dry_run_no_escribe() -> None:
    repo = _FakeRepoHistorial()
    repo.existentes["conflict|CPDL:1||"] = "persona_gana"
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    resultado = await engine.corregir_decision(
        "conflict|CPDL:1||", "atribucion_gana", decided_by="a", reason="r", apply=False
    )

    assert resultado["estado"] == "dry_run" and repo.historial_filas == []
    assert repo.existentes["conflict|CPDL:1||"] == "persona_gana"


async def test_decidir_identidad_map_to_existing() -> None:
    repo = _FakeRepo()
    repo.unidades = [_unidad("identity_cluster||viaf:1|", "viaf:1")]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    resultado = await engine.decidir_identidad(
        "viaf:1", "map_to_existing", target_person_key="viaf:2", decided_by="mgarcia", apply=True
    )

    assert resultado["insertadas"] == 1
    fila = repo.insertadas[0]
    assert fila["decision_type"] == "identity" and fila["decision"] == "map_to_existing"
    assert fila["target_person_key"] == "viaf:2" and fila["work_key"] is None
    assert json.loads(fila["evidence_json"])["decision_mode"] == "individual"


async def test_decidir_identidad_accept_sin_target() -> None:
    repo = _FakeRepo()
    repo.unidades = [_unidad("identity_cluster||viaf:1|", "viaf:1")]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    resultado = await engine.decidir_identidad("viaf:1", "accept", decided_by="a", apply=True)

    assert resultado["insertadas"] == 1 and repo.insertadas[0]["target_person_key"] is None


async def test_decidir_identidad_valida_semantica_y_existencia() -> None:
    repo = _FakeRepo()
    repo.unidades = [_unidad("identity_cluster||viaf:1|", "viaf:1")]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        await engine.decidir_identidad("viaf:1", "inventada", decided_by="a")
    with pytest.raises(ValueError):
        await engine.decidir_identidad("viaf:1", "map_to_existing", decided_by="a")  # sin target
    with pytest.raises(ValueError):
        await engine.decidir_identidad("viaf:1", "accept", target_person_key="viaf:2", decided_by="a")
    with pytest.raises(LookupError):
        await engine.decidir_identidad("viaf:999", "accept", decided_by="a")
    repo.existentes["identity||viaf:1|composer"] = "not_a_person"
    with pytest.raises(DecisionExistenteDistinta):
        await engine.decidir_identidad("viaf:1", "accept", decided_by="a")


async def test_preview_F_incluye_propuesta_candidatos_evidencia_y_colisiones() -> None:
    repo = _FakeRepo()
    repo.unidades = [{
        "item_key": "identity_cluster||name:x|", "person_key": "name:x", "role_key": None,
        "obras": 5, "roles": "composer", "estados": "ambiguous",
        "candidatos_json": json.dumps([{"person_key": "name:y"}]),
        "contexto_json": json.dumps({
            "nombres_vistos": ["x"], "colision_de_clave": True,
            "evidencia_union": ["nombre_compatible"], "patrones_origen": [{"patron": "X", "n": 3}],
        }),
    }]
    engine = ReviewEngine(repo)  # type: ignore[arg-type]

    preview = await engine.preview_tramo("F", "leave_unresolved", batch="F-0001")
    unidad = preview.filas[0]

    assert unidad["propuesta"] == "name:x" and unidad["colisiones"] is True
    assert unidad["candidatos"][0]["person_key"] == "name:y"
    assert unidad["obras_cubiertas"] == 5 and unidad["excepcion"] == "colision_de_clave"
    assert preview.excepciones[0]["person_key"] == "name:x"


def test_condiciones_tramo_F_excluye_los_estados_con_tratamiento_propio() -> None:
    condiciones, parametros = condiciones_tramo("f")

    assert any("ambiguous" in p for p in parametros)
    assert parametros.count("%sanitized%") == 1 and parametros.count("%contaminated%") == 1
    assert any("NOT LIKE" in c for c in condiciones)
    with pytest.raises(ValueError):
        condiciones_tramo("X")


def test_condiciones_tramo_A_es_ancla_tipada_resuelta_sin_otros_estados() -> None:
    condiciones, parametros = condiciones_tramo("A")

    assert parametros[-4:] == ["viaf:%", "musicbrainz:%", "mbid:%", "isni:%"]
    assert "%resolved%" in parametros and "%ambiguous%" in parametros
    assert any("person_key LIKE %s" in c for c in condiciones)
