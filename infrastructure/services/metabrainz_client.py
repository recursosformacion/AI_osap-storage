from __future__ import annotations

import json
import tarfile
import tempfile
from pathlib import Path

import httpx

_REPLICATION_INFO_URL = "https://metabrainz.org/api/musicbrainz/replication-info"
_JSON_DUMP_URL = (
    "https://metabrainz.org/api/musicbrainz/json-dumps/json-dump-{packet}/{entity}.tar.xz"
)


class MetabrainzClient:
    """Cliente de replicación de Metabrainz (espejo de MusicBrainz).

    Permite consultar el último paquete de replicación disponible (`replication-info`)
    y descargar los volcados JSON incrementales por hora y por entidad
    (`json-dump-<N>/<entity>.tar.xz`), en formato una entidad por línea.
    """

    def __init__(self, token: str, base_url: str = _REPLICATION_INFO_URL) -> None:
        self._token = token
        self._base_url = base_url

    async def last_packet(self) -> int:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._base_url, params={"token": self._token})
            resp.raise_for_status()
            data = resp.json()
            # El payload típico es {"packets": {"last": N, "list": [...]}} o {"last": N}.
            packets = data.get("packets") if isinstance(data.get("packets"), dict) else data
            last = packets.get("last") if isinstance(packets, dict) else data.get("last")
            return int(last or 0)

    async def fetch_json_dump(
        self,
        packet: int,
        entity: str,
        dest: Path,
        timeout: float = 180.0,
    ) -> Path | None:
        """Descarga `json-dump-<packet>/<entity>.tar.xz` y devuelve el fichero extraído.

        Devuelve la ruta al archivo de líneas JSON (`mbdump/<entity>`), o None si el dump
        para esa entidad no existe en ese paquete (HTTP 404).
        """
        url = _JSON_DUMP_URL.format(packet=packet, entity=entity)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params={"token": self._token})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            tmp = Path(tempfile.gettempdir()) / f"mb-{packet}-{entity}.tar.xz"
            tmp.write_bytes(resp.content)

        dest.mkdir(parents=True, exist_ok=True)
        extracted = dest / f"mbdump-{packet}-{entity}" / f"{entity}.jsonl"
        extracted.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(tmp, "r:xz") as tar:
                member = tar.getmember(f"mbdump/{entity}")
                f = tar.extractfile(member)
                if f is None:
                    return None
                with open(extracted, "wb") as out:
                    out.write(f.read())
        finally:
            tmp.unlink(missing_ok=True)
        return extracted

    @staticmethod
    def iter_lines(path: Path, *, batch: int = 500):
        """Itera las líneas JSON de un dump descargado, en lotes."""
        batch_rows: list[dict] = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    batch_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(batch_rows) >= batch:
                    yield batch_rows
                    batch_rows = []
        if batch_rows:
            yield batch_rows
