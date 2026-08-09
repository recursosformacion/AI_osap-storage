from __future__ import annotations

import asyncio

from application.use_cases.populate_composers import PopulateComposers
from domain.services.composer_names import normalize_composer_name
from tests.fakes import InMemoryComposerRepository


def _names():
    return [
        # Grupo "w a mozart" (variantes triviales)
        "W. A. Mozart", "w. a. mozart", "W A Mozart", "W. A. Mozart",
        # Grupo "wolfgang amadeus mozart"
        "Wolfgang Amadeus Mozart",
        # Desconocido / ruido que se conserva como propio grupo
        "Compositor Inexistente",
        # Vacíos se ignoran
        "", "NA", None,
    ]


def test_populate_creates_composers_and_aliases():
    repo = InMemoryComposerRepository()
    result = asyncio.run(PopulateComposers(repo).execute(_names()))
    assert result.composers == 3
    assert result.aliases == 3
    assert result.reused == 0

    # La variante trivial y la canónica completa son grupos distintos (no se fusionan).
    assert len(repo._composers) == 3
    aliases = []
    for group in repo._aliases.values():
        aliases.extend(group)
    assert len(aliases) == 3


def test_populate_is_idempotent():
    repo = InMemoryComposerRepository()
    uc = PopulateComposers(repo)
    first = asyncio.run(uc.execute(_names()))
    second = asyncio.run(uc.execute(_names()))
    assert first.composers == 3
    assert second.composers == 0
    assert second.reused == 3
    assert len(repo._composers) == 3
    assert len(repo._aliases) == 3


def test_canonical_is_most_frequent_longest():
    repo = InMemoryComposerRepository()
    asyncio.run(PopulateComposers(repo).execute(
        ["W. A. Mozart", "W. A. Mozart", "Wolfgang Amadeus Mozart"]
    ))
    # Grupo "w a mozart": "W. A. Mozart" más frecuente -> canónico
    resolved = asyncio.run(repo.resolve_by_normalized("w a mozart"))
    assert resolved is not None
    assert resolved[1] == "W. A. Mozart"
    # Grupo "wolfgang amadeus mozart"
    resolved2 = asyncio.run(repo.resolve_by_normalized("wolfgang amadeus mozart"))
    assert resolved2 is not None
    assert resolved2[1] == "Wolfgang Amadeus Mozart"


def test_populate_resolvable_from_alias():
    repo = InMemoryComposerRepository()
    asyncio.run(PopulateComposers(repo).execute(_names()))
    result = asyncio.run(repo.resolve_by_normalized(normalize_composer_name("w. a. mozart")))
    assert result is not None
    assert result[1] == "W. A. Mozart"
    assert result[0]  # id no vacío
