from __future__ import annotations

import asyncio

from application.use_cases.catalogues import CatalogueQueries
from domain.entities.catalogue import catalogue_prefix
from infrastructure.seed.catalogues import CATALOGUES
from tests.fakes import InMemoryCatalogueRepository


def _repo() -> InMemoryCatalogueRepository:
    repo = InMemoryCatalogueRepository()
    asyncio.run(repo.seed(CATALOGUES))
    return repo


def test_prefix_extraction():
    assert catalogue_prefix("K. 15h") == "K"
    assert catalogue_prefix("BWV 846") == "BWV"
    assert catalogue_prefix("Hob. XVI:1") == "Hob"
    assert catalogue_prefix("Op. 15") is None  # genérico
    assert catalogue_prefix("K") is None  # sin número/punto, ambiguo
    assert catalogue_prefix("A minor ...") is None  # tonalidad, no catálogo
    assert catalogue_prefix("") is None
    assert catalogue_prefix(None) is None


def test_by_prefix_k_mozart_and_scarlatti():
    repo = _repo()
    result = asyncio.run(CatalogueQueries(repo).by_prefix("K"))
    composers = {c.composer for c in result}
    assert "Wolfgang Amadeus Mozart" in composers
    assert "Domenico Scarlatti" in composers  # K es ambiguo


def test_by_composer():
    repo = _repo()
    result = asyncio.run(CatalogueQueries(repo).by_composer("Mozart"))
    assert result
    assert all("mozart" in c.composer.lower() for c in result)


def test_list():
    repo = _repo()
    items = asyncio.run(CatalogueQueries(repo).list(limit=5, offset=0))
    assert len(items) == 5


def test_composer_from_reference_unique_prefix():
    repo = _repo()
    q = CatalogueQueries(repo)
    # BWV -> solo J. S. Bach (único) -> compositor
    assert asyncio.run(q.composer_from_reference("BWV 846")) == "Johann Sebastian Bach"
    # K es ambiguo (Mozart y Scarlatti) -> None
    assert asyncio.run(q.composer_from_reference("K. 15h")) is None
    # Sin prefijo reconocible -> None
    assert asyncio.run(q.composer_from_reference("Sonata op. 15")) is None


def test_seed_idempotent():
    repo = _repo()
    asyncio.run(repo.seed(CATALOGUES))
    second = asyncio.run(repo.seed(CATALOGUES))
    assert second == 0
    assert len(repo._items) == len(CATALOGUES)
