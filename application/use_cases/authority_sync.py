from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from domain.entities.authority_identifier import (
    AuthorityEntityType,
    AuthorityIdentifier,
    AuthorityScheme,
)
from domain.ports.authority_identifier_repository import AuthorityIdentifierRepository
from domain.ports.authority_sync_repository import AuthoritySyncStateRepository
from infrastructure.services.metabrainz_client import MetabrainzClient

_SOURCE = "metabrainz"
_ENTITY_ARTIST = "artist"
_ENTITY_WORK = "work"


@dataclass
class SyncResult:
    source: str = _SOURCE
    packets_checked: int = 0
    packets_downloaded: int = 0
    artists_processed: int = 0
    works_processed: int = 0
    identifiers_upserted: int = 0
    skipped_packets: int = 0
    errors: list[str] = field(default_factory=list)


class SyncMetabrainzAuthority:
    """Sincroniza la autoridad (compositores/obras) desde Metabrainz.

    Estrategia: metabrainz numera las entregas (`replication-info` → `last`). El job se
    consulta diariamente, ve los números disponibles y solicita los paquetes
    `checkpoint+1 .. last` (los dumps JSON incrementales por hora y por entidad).
    Cada `artist` procesado hace upsert en `authority_identifiers` (composer→musicbrainz)
    y cada `work` en composer→musicbrainz_work, de forma idempotente.

    El checkpoint se guarda en `authority_sync_state` tras procesar cada paquete, por lo
    que el job puede interrumpirse y continuar.
    """

    def __init__(
        self,
        mb: MetabrainzClient,
        identifiers: AuthorityIdentifierRepository,
        state: AuthoritySyncStateRepository,
        tmp_root: Path | None = None,
    ) -> None:
        self._mb = mb
        self._identifiers = identifiers
        self._state = state
        self._tmp_root = tmp_root or (Path(__file__).resolve().parent.parent.parent / "data" / "tmp" / "mb-sync")

    async def execute(
        self, *, max_packets: int = 48, entities: tuple[str, ...] = (_ENTITY_ARTIST, _ENTITY_WORK)
    ) -> SyncResult:
        result = SyncResult()
        state = await self._state.get(_SOURCE)
        checkpoint = state.last_packet

        last = await self._mb.last_packet()
        if last <= checkpoint:
            return result

        pending = list(range(checkpoint + 1, last + 1))
        to_process = pending[:max_packets]
        result.packets_checked = len(pending)

        for packet in to_process:
            try:
                await self._process_packet(packet, entities, result)
                await self._state.save(
                    _SOURCE,
                    last_packet=packet,
                    last_success_at=datetime.now(UTC),
                    last_error=None,
                    metadata={
                        "last_run": {
                            "packets_downloaded": result.packets_downloaded,
                            "artists_processed": result.artists_processed,
                            "works_processed": result.works_processed,
                            "identifiers_upserted": result.identifiers_upserted,
                        }
                    },
                )
                result.packets_downloaded += 1
            except Exception as exc:  # noqa: BLE001 — el job continúa con el siguiente paquete
                message = f"paquete {packet}: {exc}"
                result.errors.append(message)
                result.skipped_packets += 1
                await self._state.save(
                    _SOURCE, last_error=message[:512], last_success_at=datetime.now(UTC)
                )
                break  # fallo de red/descarga: parar y reintentar el próximo día desde el mismo punto

        return result

    async def _process_packet(
        self, packet: int, entities: tuple[str, ...], result: SyncResult
    ) -> None:
        for entity in entities:
            path = await self._mb.fetch_json_dump(packet, entity, self._tmp_root)
            if path is None:
                continue
            if entity == _ENTITY_ARTIST:
                await self._process_artists(path, result)
            elif entity == _ENTITY_WORK:
                await self._process_works(path, result)
            path.unlink(missing_ok=True)

    async def _process_artists(self, path: Path, result: SyncResult) -> None:
        for rows in self._mb.iter_lines(path):
            for row in rows:
                artist_id = row.get("id")
                if not artist_id:
                    continue
                result.artists_processed += 1
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                await self._identifiers.upsert(
                    AuthorityIdentifier(
                        entity_type=AuthorityEntityType.COMPOSER,
                        entity_id=artist_id,
                        scheme=AuthorityScheme.MUSICBRAINZ,
                        value=artist_id,
                        source=_SOURCE,
                        confidence=1.0,
                        metadata={
                            "name": name,
                            "sort_name": row.get("sort_name"),
                            "type": row.get("type"),
                            "country": row.get("country"),
                            "gender": row.get("gender"),
                            "disambiguation": row.get("disambiguation"),
                            "life_span": row.get("life_span"),
                        },
                    )
                )
                result.identifiers_upserted += 1

    async def _process_works(self, path: Path, result: SyncResult) -> None:
        for rows in self._mb.iter_lines(path):
            for row in rows:
                work_id = row.get("id")
                if not work_id:
                    continue
                result.works_processed += 1
                title = (row.get("title") or "").strip()
                if not title:
                    continue
                await self._identifiers.upsert(
                    AuthorityIdentifier(
                        entity_type=AuthorityEntityType.WORK,
                        entity_id=work_id,
                        scheme=AuthorityScheme.MUSICBRAINZ,
                        value=work_id,
                        source=_SOURCE,
                        confidence=1.0,
                        metadata={
                            "title": title,
                            "language": row.get("language"),
                            "type": row.get("type"),
                        },
                    )
                )
                result.identifiers_upserted += 1


class SyncMetabrainzAuthorityAsJob:
    """Wrapper de `SyncMetabrainzAuthority` pensado para un job diario (cron/timer)."""

    def __init__(self, inner: SyncMetabrainzAuthority) -> None:
        self._inner = inner

    async def run(self, **kwargs) -> SyncResult:
        try:
            result = await self._inner.execute(**kwargs)
            await asyncio.sleep(0)
            return result
        except Exception as exc:  # noqa: BLE001
            return SyncResult(errors=[str(exc)])
