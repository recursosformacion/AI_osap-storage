from __future__ import annotations

import httpx

_USER_AGENT = "osap-storage/0.1 (admin@osap.local)"


class OsapApiClient:
    """Cliente del API de osap-api para resolver la identidad de un compositor.

    osap-api es el especialista en entidades externas (MusicBrainz, Wikidata, VIAF...).
    Storage le envía la obra y procesa la respuesta: status resolved|ambiguous|not_found,
    composer (canónico), confidence, input_quality, candidates[] y evidence[].
    """

    def __init__(self, base_url: str, service_token: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token

    async def resolve_composer(self, payload: dict) -> dict:
        headers = {"User-Agent": _USER_AGENT, "Content-Type": "application/json"}
        if self._service_token:
            headers["Authorization"] = f"Bearer {self._service_token}"
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(
                f"{self._base_url}/api/v1/composers/resolve",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
