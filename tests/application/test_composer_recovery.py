from __future__ import annotations

import asyncio

from application.services.composer_recovery import ComposerRecoveryService
from domain.entities.composer import Composer
from domain.entities.work import Work
from tests.fakes import InMemoryComposerRepository, InMemoryWorkRepository


class FakeOsapApi:
    def __init__(self, responses: list[dict]):
        self._responses = responses
        self.calls = []

    async def resolve_composer(self, payload: dict) -> dict:
        self.calls.append(payload)
        return self._responses.pop(0) if self._responses else {"data": {"status": "not_found"}}


def _work(title: str, work_id: int = 1, composer_id: str = "susp", catalogue=None):
    return Work(id=work_id, work_key=f"k{work_id}", title=title, composer_id=composer_id,
                catalogue=catalogue)


def _setup(responses):
    composers = InMemoryComposerRepository()
    asyncio.run(composers.create(Composer(id="susp", name="\u00d0\u00d0\u00ba \u00d0")))
    works = InMemoryWorkRepository()
    asyncio.run(works.create(_work("Song to the Auspicious Cloud - Second Version")))
    api = FakeOsapApi(responses)
    svc = ComposerRecoveryService(composers, works, api)
    return composers, works, api, svc


def test_detect_suspicious_marks_mojibake():
    composers = InMemoryComposerRepository()
    asyncio.run(composers.create(Composer(id="m", name="\u00d0\u00d0\u00d0\u00ba\u00d0")))
    asyncio.run(composers.create(Composer(id="g", name="Wolfgang Amadeus Mozart")))
    svc = ComposerRecoveryService(composers, InMemoryWorkRepository(), FakeOsapApi([]))
    stats = asyncio.run(svc.detect_suspicious())
    assert stats.detected == 1
    assert asyncio.run(composers.get_by_id("m")).suspicious is True
    assert asyncio.run(composers.get_by_id("m")).suspicious_reason == "encoding_anomaly"
    assert asyncio.run(composers.get_by_id("g")).suspicious is False


def test_resolved_applies_canonical():
    composers, works, api, svc = _setup([
        {"data": {
            "status": "resolved",
            "confidence": 0.99,
            "input_quality": "corrupt_or_suspicious",
            "composer": {"name": "Xiao Youmei", "aliases": ["Xiao", "Youmei"],
                         "external_ids": {"musicbrainz": "mb-xy"}},
            "candidates": [], "evidence": [],
        }},
    ])
    work = asyncio.run(works.get_by_id(1))
    res = asyncio.run(svc.recover(work))
    assert res.decision == "resolved"
    assert res.old_composer_id == "susp"
    # la obra pasa al compositor canónico, no al corrupto
    assert work.composer_id != "susp"
    assert asyncio.run(works.get_by_id(1)).composer_id == work.composer_id
    assert asyncio.run(works.get_by_id(1)).composer == "Xiao Youmei"
    # auditoría guardada con el envelope
    resolutions = asyncio.run(composers.list_resolutions(1))
    assert len(resolutions) == 1
    assert "status" in resolutions[0].evidence


def test_ambiguous_pending_human():
    composers, works, api, svc = _setup([
        {"data": {
            "status": "ambiguous", "composer": None, "confidence": 0.5,
            "candidates": [{"name": "Candidato A"}], "evidence": [],
        }},
    ])
    work = asyncio.run(works.get_by_id(1))
    res = asyncio.run(svc.recover(work))
    assert res.decision == "pending_human"
    assert res.reason == "ambiguous"
    assert asyncio.run(works.get_by_id(1)).composer_id == "susp"  # no cambia


def test_not_found_pending_human_no_invent():
    composers, works, api, svc = _setup([
        {"data": {"status": "not_found", "composer": None, "candidates": [], "evidence": []}},
    ])
    work = asyncio.run(works.get_by_id(1))
    res = asyncio.run(svc.recover(work))
    assert res.decision == "pending_human"
    assert res.reason == "not_found"
    assert res.candidate_composer_id is None
    assert asyncio.run(works.get_by_id(1)).composer_id == "susp"


def test_no_title_pending():
    composers = InMemoryComposerRepository()
    asyncio.run(composers.create(Composer(id="susp", name="corrupto")))
    works = InMemoryWorkRepository()
    asyncio.run(works.create(_work("", work_id=1)))
    svc = ComposerRecoveryService(composers, works, FakeOsapApi([]))
    res = asyncio.run(svc.recover(asyncio.run(works.get_by_id(1))))
    assert res.reason == "no_title"
    assert res.decision == "pending_human"


def test_recover_batch_resolved_and_skips():
    composers, works, api, svc = _setup([
        {"data": {"status": "resolved", "composer": {"name": "Xiao Youmei"}, "confidence": 0.99}},
        {"data": {"status": "not_found", "composer": None}},
    ])
    # dos obras del mismo compositor sospechoso
    asyncio.run(works.create(_work("Otra obra", work_id=2, composer_id="susp")))
    asyncio.run(composers.set_suspicious("susp", True, "encoding_anomaly"))
    stats = asyncio.run(svc.recover_batch(limit=5))
    assert stats.recovered == 1
    assert stats.pending_human == 1
