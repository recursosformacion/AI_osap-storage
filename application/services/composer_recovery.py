from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import dataclass, replace

from domain.entities.composer import (
    Composer,
    ComposerResolution,
    ComposerResolutionDecision,
    ComposerSummary,
)
from domain.entities.work import Work
from domain.ports.composer_repository import ComposerRepository
from domain.ports.work_repository import WorkRepository
from domain.services.composer_quality import is_mojibake
from infrastructure.services.osap_api_client import OsapApiClient

RESOLVER_VERSION = "composer-recovery-v3"


@dataclass(frozen=True)
class RecoveryStats:
    detected: int = 0
    recovered: int = 0
    pending_human: int = 0
    no_title: int = 0
    errors: int = 0


class ComposerRecoveryService:
    """Recupera la identidad del compositor partiendo de la OBRA (no del nombre corrupto).

    Storage NO consulta entidades externas: es responsabilidad de osap-api
    (`POST /api/v1/composers/resolve`). Storage le envía la obra y procesa la respuesta:
    - resolved: el compositor es la identidad canónica -> aplicar a la obra.
    - ambiguous: hay candidatos -> revisión humana (pending_human).
    - not_found: sin candidatos -> no inventar (pending_human).
    - input_quality corrupt_or_suspicious: un nombre corrupto nunca se convierte en canónico
      (lo resuelve osap-api a partir de la obra).
    Se guarda un `composer_resolution` (auditoría) y el dato original corrupto no se destruye.
    """

    def __init__(
        self,
        composers: ComposerRepository,
        works: WorkRepository,
        osap_api: OsapApiClient,
    ) -> None:
        self._composers = composers
        self._works = works
        self._osap_api = osap_api

    async def detect_suspicious(self, *, limit: int = 1000) -> RecoveryStats:
        stats = RecoveryStats()
        offset = 0
        while True:
            batch = await self._composers.list_summaries(limit=limit, offset=offset)
            if not batch:
                break
            for item in batch:
                if is_mojibake(item.name):
                    await self._composers.set_suspicious(item.id, True, "encoding_anomaly")
                    stats = replace(stats, detected=stats.detected + 1)
            offset += limit
        return stats

    async def recover_batch(self, *, limit: int = 50) -> RecoveryStats:
        stats = RecoveryStats()
        processed = 0
        offset = 0
        while processed < limit:
            suspicious = await self._composers.list_suspicious(limit=limit, offset=offset)
            if not suspicious:
                break
            for composer in suspicious:
                works = await self._works.list_by_composer(composer.id, limit=limit, offset=0)
                for work in works:
                    if processed >= limit:
                        return stats
                    resolution = await self.recover(work, old_composer=composer)
                    if resolution.decision == "resolved":
                        stats = replace(stats, recovered=stats.recovered + 1)
                    elif resolution.reason == "error":
                        stats = replace(stats, errors=stats.errors + 1)
                    else:
                        stats = replace(stats, pending_human=stats.pending_human + 1)
                    processed += 1
            offset += limit
        return stats

    async def recover(
        self, work: Work, *, old_composer: ComposerSummary | None = None
    ) -> ComposerResolution:
        old_id = work.composer_id
        if not work.title:
            resolution = ComposerResolution(
                work_id=work.id, old_composer_id=old_id, reason="no_title",
                resolver_version=RESOLVER_VERSION,
                decision=ComposerResolutionDecision.PENDING_HUMAN,
            )
            return await self._composers.record_resolution(resolution)

        payload = _build_payload(work, composer_name=old_composer.name if old_composer else None)
        try:
            envelope = await self._osap_api.resolve_composer(payload)
        except Exception:
            resolution = ComposerResolution(
                work_id=work.id, old_composer_id=old_id, reason="error",
                resolver_version=RESOLVER_VERSION,
                decision=ComposerResolutionDecision.PENDING_HUMAN,
            )
            return await self._composers.record_resolution(resolution)

        data = envelope.get("data", {}) or {}
        status = data.get("status") or "not_found"
        confidence = float(data.get("confidence") or 0)
        input_quality = data.get("input_quality") or "normal"
        api_composer = data.get("composer") or None
        candidates = data.get("candidates", []) or []
        evidence = data.get("evidence", []) or []

        evidence_json = json.dumps(
            {
                "status": status,
                "input_quality": input_quality,
                "confidence": confidence,
                "candidates": candidates,
                "evidence": evidence,
            },
            ensure_ascii=False,
        )

        resolution = ComposerResolution(
            work_id=work.id,
            old_composer_id=old_id,
            candidate_composer_id=None,
            reason=status,
            evidence=evidence_json,
            confidence=confidence,
            resolver_version=RESOLVER_VERSION,
            decision=ComposerResolutionDecision.PENDING_HUMAN,
        )

        if status == "resolved" and api_composer:
            canonical = await self._apply_canonical(work, api_composer)
            resolution.candidate_composer_id = canonical.id
            resolution.decision = "resolved"
        return await self._composers.record_resolution(resolution)

    async def _apply_canonical(self, work: Work, api_composer: dict) -> Composer:
        name = (api_composer.get("name") or "").strip()
        composer = await self._composers.get_by_name(name) if name else None
        if composer is None and name:
            composer = await self._composers.create(Composer(id="", name=name))
        if composer is None:
            raise ValueError("osap-api resolved sin nombre de compositor")

        external_ids = api_composer.get("external_ids") or {}
        mbid = external_ids.get("musicbrainz") or external_ids.get("mbid")
        if mbid and not composer.musicbrainz_id:
            await self._composers.set_musicbrainz_id(composer.id, mbid)

        from domain.services.composer_names import normalize_composer_name

        aliases = api_composer.get("aliases") or []
        for alias in aliases:
            a = (alias or "").strip()
            if not a:
                continue
            with suppress(Exception):
                await self._composers.add_alias(
                    composer.id, a, normalize_composer_name(a)
                )

        work.composer_id = composer.id
        work.composer = name
        await self._works.update(work)
        return composer


def _build_payload(work: Work, *, composer_name: str | None) -> dict:
    return {
        "work": {
            "title": work.title,
            "catalog": work.catalogue,
            "year": extract_year(work.title),
        },
        "composer": {"name": composer_name} if composer_name else None,
        "source": {"provider": "pdmx", "source_work_id": work.work_key},
        "representations": [{"title": work.title, "provider": "pdmx", "format": "musicxml"}],
    }


def extract_year(title: str | None) -> int | None:
    import re

    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", title or "")
    return int(m.group(1)) if m else None
