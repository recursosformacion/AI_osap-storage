from __future__ import annotations

import asyncio

from application.services.composer_recovery import ComposerRecoveryService
from domain.entities.composer import Composer, ComposerResolutionDecision
from domain.entities.work import Work
from tests.fakes import InMemoryComposerRepository, InMemoryWorkRepository


class FakeMB:
    def __init__(self, works_by_title: dict[str, list[dict]]):
        self._data = works_by_title
        self.calls = []

    async def search_works(self, title: str) -> list[dict]:
        self.calls.append(title)
        return self._data.get(title, [])


def _work(title: str, work_id: int = 1, composer_id: str = "susp"):
    return Work(id=work_id, work_key=f"k{work_id}", title=title, composer_id=composer_id)


def _mb_work(title: str, composer: str, mbid: str) -> dict:
    return {
        "title": title,
        "relations": [
            {"type": "composer",
             "artist": {"name": composer, "id": mbid, "type": "Person"}},
        ],
    }


def _setup(title, mb_works):
    composers = InMemoryComposerRepository()
    asyncio.run(composers.create(Composer(id="susp", name="\u00d0\u00d0\u00ba \u00d0")))
    works = InMemoryWorkRepository()
    asyncio.run(works.create(_work(title)))
    mb = FakeMB({title: mb_works})
    svc = ComposerRecoveryService(composers, works, mb)
    return composers, works, mb, svc


def test_detect_suspicious_marks_mojibake():
    composers = InMemoryComposerRepository()
    asyncio.run(composers.create(Composer(id="m", name="\u00d0\u00d0\u00d0\u00ba\u00d0")))
    asyncio.run(composers.create(Composer(id="g", name="Wolfgang Amadeus Mozart")))
    svc = ComposerRecoveryService(composers, InMemoryWorkRepository(), FakeMB({}))
    stats = asyncio.run(svc.detect_suspicious())
    assert stats.detected == 1
    assert asyncio.run(composers.get_by_id("m")).suspicious is True
    assert asyncio.run(composers.get_by_id("m")).suspicious_reason == "encoding_anomaly"
    assert asyncio.run(composers.get_by_id("g")).suspicious is False


def test_recover_auto_corrects_with_high_confidence():
    composers, works, mb, svc = _setup(
        "Song to the Auspicious Cloud",
        [_mb_work("Song to the Auspicious Cloud", "Xiao Youmei", "mb-xy")],
    )
    work = asyncio.run(works.get_by_id(1))
    res = asyncio.run(svc.recover(work))
    assert res.decision == ComposerResolutionDecision.AUTO_CORRECT
    assert res.old_composer_id == "susp"
    assert res.confidence >= 0.9
    # se crea el candidato y se reasigna la obra
    assert work.composer_id != "susp"
    assert asyncio.run(works.get_by_id(1)).composer_id == work.composer_id
    # auditoría guardada
    resolutions = asyncio.run(composers.list_resolutions(1))
    assert len(resolutions) == 1


def test_recover_pending_human_when_no_match():
    composers, works, mb, svc = _setup("Song to the Auspicious Cloud", [])
    work = asyncio.run(works.get_by_id(1))
    res = asyncio.run(svc.recover(work))
    assert res.decision == ComposerResolutionDecision.PENDING_HUMAN
    assert res.candidate_composer_id is None
    # la obra NO cambia de compositor
    assert asyncio.run(works.get_by_id(1)).composer_id == "susp"


def test_recover_no_title_pending():
    composers = InMemoryComposerRepository()
    asyncio.run(composers.create(Composer(id="susp", name="corrupto")))
    works = InMemoryWorkRepository()
    asyncio.run(works.create(_work("", work_id=1)))
    svc = ComposerRecoveryService(composers, works, FakeMB({}))
    work = asyncio.run(works.get_by_id(1))
    res = asyncio.run(svc.recover(work))
    assert res.reason == "no_title"
    assert res.decision == ComposerResolutionDecision.PENDING_HUMAN


def test_recover_batch():
    composers, works, mb, svc = _setup(
        "Song to the Auspicious Cloud",
        [_mb_work("Song to the Auspicious Cloud", "Xiao Youmei", "mb-xy")],
    )
    asyncio.run(composers.set_suspicious("susp", True, "encoding_anomaly"))
    stats = asyncio.run(svc.recover_batch(limit=5))
    assert stats.recovered >= 1
