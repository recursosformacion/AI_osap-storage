from __future__ import annotations

from dataclasses import dataclass

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
from infrastructure.services.musicbrainz_client import MusicBrainzClient

RESOLVER_VERSION = "composer-recovery-v1"
AUTO_THRESHOLD = 0.9


@dataclass(frozen=True)
class RecoveryStats:
    detected: int = 0
    recovered: int = 0
    pending_human: int = 0
    no_title: int = 0


class ComposerRecoveryService:
    """Recupera la identidad de compositores partiendo de la OBRA, no del nombre corrupto.

    Flujo:
    1. `detect_suspicious`: marca como sospechosos los compositores con nombre corrupto
       (encoding) sin cambiar el valor original.
    2. `recover(work)`: para una obra con compositor sospechoso, extrae la identidad del
       título, busca evidencias independientes (MusicBrainz `work` -> compositor), calcula
       confianza y guarda un `composer_resolution` (auditoría). Si la confianza es alta,
       corrige `work.composer_id`; si es débil, queda para revisión humana.
    El dato original corrupto nunca se destruye: queda como `old_composer_id`/evidencia.
    """

    def __init__(
        self,
        composers: ComposerRepository,
        works: WorkRepository,
        mb: MusicBrainzClient,
    ) -> None:
        self._composers = composers
        self._works = works
        self._mb = mb

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
                    stats = RecoveryStats(detected=stats.detected + 1)
            offset += limit
        return stats

    async def recover_batch(self, *, limit: int = 50) -> RecoveryStats:
        """Recupera la identidad de un lote de obras con compositor sospechoso."""
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
                    if resolution.decision == ComposerResolutionDecision.AUTO_CORRECT:
                        stats = RecoveryStats(recovered=stats.recovered + 1)
                    else:
                        stats = RecoveryStats(pending_human=stats.pending_human + 1)
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

        evidence: list[str] = []
        candidate = await self._mb_composer_for_title(work.title, evidence)

        if candidate is None:
            resolution = ComposerResolution(
                work_id=work.id, old_composer_id=old_id, reason="no_match",
                evidence="\n".join(evidence),
                resolver_version=RESOLVER_VERSION,
                decision=ComposerResolutionDecision.PENDING_HUMAN,
            )
            return await self._composers.record_resolution(resolution)

        candidate_name, mbid = candidate
        confidence = await self._confidence(work, candidate_name, evidence)
        decision = (
            ComposerResolutionDecision.AUTO_CORRECT
            if confidence >= AUTO_THRESHOLD
            else ComposerResolutionDecision.PENDING_HUMAN
        )
        resolution = ComposerResolution(
            work_id=work.id,
            old_composer_id=old_id,
            candidate_composer_id=None,
            reason="work_identity",
            evidence="\n".join(evidence),
            confidence=confidence,
            resolver_version=RESOLVER_VERSION,
            decision=decision,
        )

        if decision == ComposerResolutionDecision.AUTO_CORRECT:
            composer = await self._get_or_create(candidate_name, mbid)
            resolution.candidate_composer_id = composer.id
            work.composer_id = composer.id
            await self._works.update(work)
        return await self._composers.record_resolution(resolution)

    async def _mb_composer_for_title(
        self, title: str, evidence: list[str]
    ) -> tuple[str, str | None] | None:
        try:
            works = await self._mb.search_works(title)
        except Exception:
            return None
        if not works:
            return None
        evidence.append(f"musicbrainz_work_hits={len(works)}")
        title_norm = normalize_title(title)
        for mb_work in works:
            if normalize_title(mb_work.get("title")) == title_norm:
                evidence.append("title_exact_match")
            relations = mb_work.get("relations", [])
            for rel in relations:
                if rel.get("type") in ("composer", "writer", "lyricist"):
                    artist = rel.get("artist") or {}
                    name = (artist.get("name") or "").strip()
                    if name and (artist.get("type") or "").lower() == "person":
                        evidence.append(
                            f"work='{mb_work.get('title')}' -> composer='{name}' (mbid={artist.get('id')})"
                        )
                        return name, artist.get("id")
        return None

    async def _confidence(
        self, work: Work, candidate_name: str, evidence: list[str]
    ) -> float:
        # Señales explícitas de confianza (0..1).
        c = 0.0
        title_norm = normalize_title(work.title)
        # El candidato proviene de una obra de MusicBrainz con relación de compositor.
        c += 0.5
        # Coincidencia exacta del título con la obra de MusicBrainz (señal fuerte).
        if "title_exact_match" in evidence:
            c += 0.4
        # Coincidencia del nombre del compositor en el título (señal débil).
        for token in candidate_name.lower().split():
            if token and token in title_norm:
                c += 0.2
                break
        return min(1.0, c)

    async def _get_or_create(self, name: str, mbid: str | None) -> Composer:
        existing = await self._composers.get_by_name(name)
        if existing is not None:
            if mbid and not existing.musicbrainz_id:
                await self._composers.set_musicbrainz_id(existing.id, mbid)
            return existing
        composer = await self._composers.create(Composer(id="", name=name))
        if mbid:
            await self._composers.set_musicbrainz_id(composer.id, mbid)
        await self._composers.add_alias(
            composer.id, name, normalize_alias(name)
        )
        return composer


def normalize_alias(name: str) -> str:
    from domain.services.composer_names import normalize_composer_name

    return normalize_composer_name(name)


def normalize_title(title: str | None) -> str:
    """Normaliza un título para comparar coincidencias (minúsculas, sin espacios dobles)."""
    return " ".join((title or "").strip().lower().split())
