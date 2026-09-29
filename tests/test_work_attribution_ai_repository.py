"""Tests del repositorio de atribución IA: atomicidad, rowcount y resolución canónica.

Se usa un doble de `Database` (sin MySQL) que registra las sentencias y simula `rowcount`, de
modo que se puede verificar que la aceptación es transaccional y que no acepta sin insertar.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest
from domain.exceptions import ProposalAssignmentError, ProposalStateError
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

    def __init__(self, rowcounts: list[int]) -> None:
        self._rowcounts = rowcounts
        self.log: list[tuple[str, object]] = []
        self.committed = False
        self.rolled_back = False

    @asynccontextmanager
    async def transaction(self) -> Any:
        cursor = _Cursor([], self._rowcounts, self.log)
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
    assert "INSERT IGNORE INTO works_person_roles" in statements[0]
    assert "INSERT INTO work_attribution_audit" in statements[1]
    assert "UPDATE work_person_ai_proposals" in statements[2]
    assert "status='pending'" in statements[2]
    # La evidencia se guarda como JSON de lista una sola vez (no doblemente codificada).
    audit_params = db.log[1][1]
    assert isinstance(audit_params, tuple)
    assert json.loads(str(audit_params[-2])) == [{"type": "source_metadata", "text": "PDMX"}]


async def test_accept_sin_fila_real_no_acepta_ni_audita() -> None:
    db = _TransactionDb(rowcounts=[0])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    with pytest.raises(ProposalAssignmentError):
        await repo.accept_proposal(
            work_id=1, person_id="p1", role_id=1, confidence=None, proposal_id=7,
            evidence=[], created_by="admin-1", note=None,
        )

    assert db.rolled_back is True
    assert db.committed is False
    assert len(db.log) == 1  # no se escribió auditoría ni estado


async def test_accept_con_estado_ya_cambiado_hace_rollback() -> None:
    db = _TransactionDb(rowcounts=[1, 1, 0])
    repo = SqlWorkAttributionAiRepository(db)  # type: ignore[arg-type]

    with pytest.raises(ProposalStateError):
        await repo.accept_proposal(
            work_id=1, person_id="p1", role_id=1, confidence=None, proposal_id=7,
            evidence=[], created_by="admin-1", note=None,
        )

    assert db.rolled_back is True
    assert len(db.log) == 3


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
