"""Tests del repositorio de atribución IA: atomicidad, rowcount y resolución canónica.

Se usa un doble de `Database` (sin MySQL) que registra las sentencias y simula `rowcount`, de
modo que se puede verificar que la aceptación es transaccional y que no acepta sin insertar.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest
from domain.exceptions import ProposalStateError
from infrastructure.repositories.sql_work_attribution_ai_repository import (
    SqlWorkAttributionAiRepository,
)


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]], rowcounts: list[int], log: list[tuple[str, object]]) -> None:
        self._rows = rows
        self._rowcounts = rowcounts
        self._log = log
        self.rowcount = 0
        self.lastrowid = 1

    async def __aenter__(self) -> _Cursor:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def execute(self, sql: str, params: object = None) -> None:
        self._log.append((" ".join(sql.split()), params))
        self.rowcount = self._rowcounts.pop(0) if self._rowcounts else 1

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    async def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _TransactionDb:
    """Doble de `Database.transaction()` que registra sentencias y si hubo rollback."""

    def __init__(self, rowcounts: list[int], rows: list[dict[str, Any]] | None = None) -> None:
        self._rowcounts = rowcounts
        self._rows = rows or []
        self.log: list[tuple[str, object]] = []
        self.committed = False
        self.rolled_back = False

    @asynccontextmanager
    async def transaction(self) -> Any:
        cursor = _Cursor(self._rows, self._rowcounts, self.log)
        try:
            yield _Conn(cursor)
            self.committed = True
        except Exception:
            self.rolled_back = True
            raise


class _Conn:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor


class _QueueDb:
    """Doble de `Database.connection()` que devuelve una tanda de filas por llamada."""

    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self._batches = list(batches)
        self.log: list[tuple[str, object]] = []

    @asynccontextmanager
    async def connection(self) -> Any:
        rows = self._batches.pop(0) if self._batches else []
        cursor = _Cursor(rows, [], self.log)
        yield _Conn(cursor)


async def test_accept_escribe_relacion_auditoria_y_estado_en_una_transaccion() -> None:
    db = _TransactionDb(rowcounts=[1, 1, 1])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    await repo.accept_proposal(
        work_id=310455, person_id="p1", role_id=1, confidence=0.96, proposal_id=7,
        evidence='[{"type": "source_metadata", "text": "PDMX"}]', created_by="admin-1", note="ok",
    )

    assert db.committed is True
    assert db.rolled_back is False
    statements = [sql for sql, _ in db.log]
    assert statements[0].startswith("SELECT 1 FROM works_person_roles")
    assert statements[1].startswith("INSERT INTO works_person_roles")
    assert statements[2].startswith("INSERT INTO work_attribution_audit")
    assert statements[3].startswith("UPDATE work_person_ai_proposals")
    assert "status='pending'" in statements[3]
    # La evidencia se guarda como JSON de lista una sola vez (no doblemente codificada).
    audit_params = db.log[2][1]
    assert isinstance(audit_params, tuple)
    assert json.loads(str(audit_params[-2])) == [{"type": "source_metadata", "text": "PDMX"}]


async def test_accept_idempotente_si_la_relacion_ya_existe() -> None:
    # El SELECT encuentra la relación → no inserta, pero acepta (antes hacía rollback).
    db = _TransactionDb(rowcounts=[1, 1, 1], rows=[{"1": 1}])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    await repo.accept_proposal(
        work_id=1, person_id="p1", role_id=1, confidence=None, proposal_id=7,
        evidence=[], created_by="admin-1", note=None,
    )

    assert db.committed is True
    assert db.rolled_back is False
    statements = [sql for sql, _ in db.log]
    assert statements[0].startswith("SELECT 1 FROM works_person_roles")
    assert not any(s.startswith("INSERT INTO works_person_roles") for s in statements)
    assert statements[1].startswith("INSERT INTO work_attribution_audit")
    assert statements[2].startswith("UPDATE work_person_ai_proposals")


async def test_accept_con_estado_ya_cambiado_hace_rollback() -> None:
    db = _TransactionDb(rowcounts=[1, 1, 1, 0])  # SELECT, INSERT, audit, UPDATE(0)
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    with pytest.raises(ProposalStateError):
        await repo.accept_proposal(
            work_id=1, person_id="p1", role_id=1, confidence=None, proposal_id=7,
            evidence=[], created_by="admin-1", note=None,
        )

    assert db.rolled_back is True
    assert len(db.log) == 4


async def test_rechazo_exige_estado_pending() -> None:
    db = _TransactionDb(rowcounts=[0])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    with pytest.raises(ProposalStateError):
        await repo.set_review_if_pending(7, "rejected", "admin-1", None)

    assert db.rolled_back is True
    assert "status='pending'" in db.log[0][0]


async def test_candidatos_resuelven_alias_canonico_y_descartan_fusionadas_u_ocultas() -> None:
    db = _QueueDb(
        [
            [{"id": "p1"}, {"id": "p2"}],
            [
                {"id": "p1", "name": "Duplicado", "persons_status": "active", "persons_visible": 1,
                 "persons_merged_into": "p3"},
                {"id": "p2", "name": "Ana Real", "persons_status": "active", "persons_visible": 1,
                 "persons_merged_into": None},
            ],
            [
                {"id": "p3", "name": "Canónica", "persons_status": "active", "persons_visible": 1,
                 "persons_merged_into": None},
                {"id": "p4", "name": "Oculta", "persons_status": "active", "persons_visible": 0,
                 "persons_merged_into": None},
            ],
        ]
    )
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    candidates = await repo.find_person_candidates("ana real")

    assert [c["name"] for c in candidates] == ["Ana Real", "Canónica"]


async def test_candidatos_sin_normalizado_no_consulta() -> None:
    db = _QueueDb([])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]
    assert await repo.find_person_candidates("") == []
    assert db.log == []


async def test_generos_se_leen_de_work_genres() -> None:
    db = _QueueDb([[{"name": "Canción"}, {"name": "Motete"}]])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    genre = await repo.work_genres(310455)

    assert genre == "Canción, Motete"
    sql = db.log[0][0]
    assert "FROM work_genres" in sql and "JOIN genres" in sql


async def test_generos_vacios_devuelven_none() -> None:
    db = _QueueDb([[]])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]
    assert await repo.work_genres(1) is None


async def test_ultima_propuesta_no_filtra_por_estado() -> None:
    db = _QueueDb([[{"id": 9, "work_id": 1, "status": "rejected"}]])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    latest = await repo.latest_proposal_for_work(1)

    assert latest is not None and latest["status"] == "rejected"
    sql = db.log[0][0]
    assert "status <>" not in sql
    assert "ORDER BY id DESC LIMIT 1" in sql


async def test_listado_no_carga_answer_json() -> None:
    db = _QueueDb([[{"total": 1}]])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    await repo.list_proposals("pending", 50, 0)

    page_sql = db.log[1][0]
    assert "SELECT *" not in page_sql
    assert "answer_json" not in page_sql
    assert "evidence_json" in page_sql  # la tarjeta muestra la evidencia


async def test_upsert_review_no_pisa_decision_humana() -> None:
    db = _TransactionDb(rowcounts=[1])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    review_id = await repo.upsert_review(
        work_id=3, batch_id="lote-1", attribution_status="traditional", attribution_note=None,
        attribution_confidence=0.9, contradictions=["título vs catálogo"],
        context={"work_id": 3, "title": "X"},
    )

    assert review_id == 1
    sql = db.log[0][0]
    assert "INSERT INTO work_ai_reviews" in sql
    assert "status='reviewed', attribution_status" in sql  # no pisa la atribución decidida
    assert "status=IF(status='reviewed', status, VALUES(status))" in sql
    assert db.committed is True


async def test_add_review_relation_no_pisa_decision_humana() -> None:
    db = _TransactionDb(rowcounts=[1])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    await repo.add_review_relation(
        review_id=1, work_id=254128, person_id="p9", person_name="Jan Novák", role_id=3,
        origin="gemini", confidence=0.4, evidence=[{"type": "editorial", "text": "arreglo"}],
    )

    sql = db.log[0][0]
    params = db.log[0][1]
    assert "INSERT INTO work_ai_review_relations" in sql
    assert "person_name_norm" in sql and "'pending',%s,%s,%s" in sql
    assert "person_id=IF(decision='pending'" in sql
    assert "confidence=IF(decision='pending'" in sql
    assert isinstance(params, tuple)
    assert params[4] == "jan novak"  # normalización canónica para el índice único
    assert json.loads(str(params[-1])) == [{"type": "editorial", "text": "arreglo"}]


async def test_decision_de_relacion_actualiza_solo_la_decision() -> None:
    db = _TransactionDb(rowcounts=[1, 1], rows=[{"review_id": 1, "work_id": 254128}])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    row = await repo.set_relation_decision(7, "accepted", reviewed_by="e2e-admin")

    assert row == {"review_id": 1, "work_id": 254128}
    sql = db.log[0][0]
    assert sql.startswith("UPDATE work_ai_review_relations SET decision=%s, decided_by=%s")
    assert db.log[0][1] == ("accepted", "e2e-admin", 7)
    assert db.committed is True


async def test_decision_de_relacion_inexistente_no_escribe() -> None:
    db = _TransactionDb(rowcounts=[0])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    assert await repo.set_relation_decision(404, "accepted") is None

    assert db.rolled_back is False
    assert len(db.log) == 1  # solo el UPDATE que no encontró fila


async def test_ensure_review_hereda_la_atribucion_de_la_propuesta_ia() -> None:
    db = _TransactionDb(rowcounts=[1])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    review_id = await repo.ensure_review(254139)

    assert review_id == 1
    sql = db.log[0][0]
    assert "SELECT %s, COALESCE((SELECT p.resolution FROM work_person_ai_proposals p" in sql
    assert "'unknown'" in sql  # solo como respaldo si no hay propuesta


async def test_alta_humana_no_pierde_evidencia_al_redecidir() -> None:
    db = _TransactionDb(rowcounts=[1])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    await repo.upsert_human_relation(
        review_id=1, work_id=254139, person_id="p1", person_name="Louise Farrenc", role_id=3,
        decision="accepted", evidence=[{"type": "revisor", "text": "arreglo"}], decided_by="admin",
    )

    sql = db.log[0][0]
    assert "origin='human'" in sql and "decided_by=VALUES(decided_by)" in sql
    assert "evidence_json=IF(VALUES(evidence_json) IN ('[]', 'null'), evidence_json" in sql
