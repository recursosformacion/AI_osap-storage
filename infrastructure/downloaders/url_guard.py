"""Validación anti-SSRF de URLs de descarga externas.

Bloquea esquemas distintos de http/https y destinos que resuelven a loopback, redes
privadas, link-local, reservadas, multicast o no especificadas. Se debe aplicar a la URL
inicial y a cada redirección.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from domain.exceptions import DownloadFailed

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # `is_global` cubre loopback, privadas, link-local, reservadas, multicast, unspecified
    # y espacio compartido (100.64/10); se bloquea todo lo que no sea enrutable públicamente.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return not ip.ipv4_mapped.is_global
    return not ip.is_global


def validate_public_url(url: str) -> None:
    """Lanza `DownloadFailed` si la URL no es http/https o apunta a un destino interno."""
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise DownloadFailed(f"esquema no permitido: {parts.scheme or '(vacío)'}")
    host = parts.hostname
    if not host:
        raise DownloadFailed("URL sin host")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise DownloadFailed(f"no se pudo resolver el host: {host}") from exc
    for info in infos:
        address = str(info[4][0])
        if _is_blocked_ip(ipaddress.ip_address(address)):
            raise DownloadFailed(f"destino no permitido: {host} ({address})")
