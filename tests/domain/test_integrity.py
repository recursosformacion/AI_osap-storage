from __future__ import annotations

from domain.services.integrity import IntegrityService

SHA = "a" * 64


class FakeHasher:
    def __init__(self, digest: str) -> None:
        self.digest = digest

    async def sha256_file(self, path: str) -> str:
        return self.digest


async def test_verify_matching_sha256():
    service = IntegrityService(FakeHasher(SHA))
    assert await service.verify(SHA, "/tmp/file") is True


async def test_verify_mismatching_sha256():
    service = IntegrityService(FakeHasher(SHA))
    assert await service.verify("b" * 64, "/tmp/file") is False


async def test_verify_ignores_case():
    service = IntegrityService(FakeHasher(SHA))
    assert await service.verify(SHA.upper(), "/tmp/file") is True


async def test_compute_returns_digest():
    service = IntegrityService(FakeHasher(SHA))
    assert await service.compute_sha256("/tmp/file") == SHA
