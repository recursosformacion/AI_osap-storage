from __future__ import annotations

import asyncio

import pytest
from application.use_cases.composer_admin import (
    ClassifyComposers,
    CleanComposerNames,
    ListComposers,
    ReviewComposer,
)
from domain.entities.composer import Composer
from domain.exceptions import EntityNotFound
from domain.services.composer_quality import (
    PARTICULAS_VALIDAS,
    REVIEW_CORRECT,
    REVIEW_INCORRECT,
    REVIEW_NOT_REVIEWED,
    classify_composer_name,
    clean_composer_name,
    extract_composer_name,
    is_mojibake,
    is_suspicious,
)
from tests.fakes import InMemoryComposerRepository


def test_clean_composer_name_removes_symbols():
    assert clean_composer_name("W. A. Mozart!!") == "W A Mozart"
    assert clean_composer_name("Mozart…") == "Mozart"
    assert clean_composer_name("A minor Alexander Gillet 1779") == "A minor Alexander Gillet"
    assert clean_composer_name("Jose  Maria   López") == "Jose Maria López"
    assert clean_composer_name("O'Connor") == "O Connor"
    assert clean_composer_name("-By Mr Clark") == "By Mr Clark"
    assert clean_composer_name("\u2018By Mr Clark\u2019 'In different hand C") == "By Mr Clark In different hand C"
    assert clean_composer_name("Jean-Baptiste Lully") == "Jean-Baptiste Lully"
    assert {"de", "del", "van", "von", "di", "da", "y",
                                  "la", "le", "dos", "den"} == PARTICULAS_VALIDAS


def test_clean_renames_existing():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="a", name="W. A. Mozart!!")))
    result = asyncio.run(CleanComposerNames(repo).execute())
    assert result["renamed"] == 1
    assert asyncio.run(repo.get_by_id("a")).name == "W A Mozart"


def test_clean_merges_collision():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="a", name="Johann Sebastian Bach!!")))
    asyncio.run(repo.create(Composer(id="b", name="Johann Sebastian Bach")))
    repo.set_work(1, "a", "Obra de A")
    result = asyncio.run(CleanComposerNames(repo).execute())
    assert result["merged"] == 1
    # a queda merged en b
    assert asyncio.run(repo.get_by_id("a")).status == "merged"
    assert asyncio.run(repo.get_by_id("b")).status == "active"
    # la obra de a pasa a b
    detail = asyncio.run(repo.get_detail("b"))
    assert detail.works_count == 1


def test_unknown_composer_ensure_idempotent():
    from domain.entities.composer import UNKNOWN_COMPOSER, UNKNOWN_COMPOSER_ID

    repo = InMemoryComposerRepository()
    c = asyncio.run(repo.ensure_unknown_composer())
    assert c.id == UNKNOWN_COMPOSER_ID
    assert c.name == UNKNOWN_COMPOSER
    # idempotente
    again = asyncio.run(repo.ensure_unknown_composer())
    assert again.id == UNKNOWN_COMPOSER_ID
    assert len(repo._composers) == 1


def test_extract_composer_name_after_marker():
    assert extract_composer_name("Attributed to William Bird") == "William Bird"
    assert extract_composer_name("Tune is A Gigg by William Bird") == "William Bird"
    assert extract_composer_name("Claude Debussy arr. Andrew Hearn") == "Claude Debussy"
    assert extract_composer_name("Claude Debussy [arranged from]") == "Claude Debussy"


def test_extract_composer_name_with_ner():
    # NER recupera el nombre dentro de texto ruidoso (si el modelo está disponible).
    assert extract_composer_name("A bluegrass song gone haywire David Ladue") == "David Ladue"
    assert extract_composer_name("Wolfgang Amadeus Mozart") == "Wolfgang Amadeus Mozart"
    assert extract_composer_name("Mozart") == "Mozart"


def test_extract_composer_name_rejects_noise():
    assert extract_composer_name("A bluegrass song gone haywire") is None
    assert extract_composer_name("") is None
    assert extract_composer_name("76") is None


def test_is_mojibake_detection():
    assert is_mojibake("\u00d0\u00d0\u00d0\u00ba\u00d0 \u00d0\u00d0\u00d1") is True  # ÐÐÐºÐ
    assert is_mojibake("ç\u00e5 ååª Kataoka Kenta") is True
    assert is_mojibake("texto con \ufffd corrompido") is True
    # Nombres válidos NO son mojibake (incl. cirílico/chino/japonés reales)
    assert is_mojibake("Wolfgang Amadeus Mozart") is False
    assert is_mojibake("Пётр Ильич Чайковский") is False  # cirílico correcto
    assert is_mojibake("武満徹") is False  # japonés correcto
    assert is_mojibake("José María") is False  # acentos latinos


def test_classify_marks_mojibake_incorrect_and_keeps_cyrillic():
    assert classify_composer_name("\u00d0\u00d0\u00d0\u00ba\u00d0 \u00d0") == REVIEW_INCORRECT
    # Cirílico válido: no es corrupción; no se puede validar -> not_reviewed (no incorrect)
    assert classify_composer_name("Пётр Ильич Чайковский") == REVIEW_NOT_REVIEWED
    # Nombre latino normal sigue correct
    assert classify_composer_name("Wolfgang Amadeus Mozart") == REVIEW_CORRECT


def test_extract_rejects_mojibake():
    assert extract_composer_name("\u00d0\u00d0\u00d0\u00ba\u00d0 \u00d0\u00d0") is None


def test_populate_skips_mojibake():
    from application.use_cases.populate_composers import PopulateComposers

    repo = InMemoryComposerRepository()
    asyncio.run(PopulateComposers(repo).execute(
        ["Wolfgang Amadeus Mozart", "\u00d0\u00d0\u00d0\u00ba\u00d0 \u00d0\u00d0"]
    ))
    names = [c.name for c in repo._composers.values()]
    assert names == ["Wolfgang Amadeus Mozart"]


def test_flag_mojibake_marks_incorrect_even_if_correct():
    from application.use_cases.composer_admin import FlagMojibakeComposers

    repo = InMemoryComposerRepository()
    # un mojibake que quedó 'correct' (de antes del detector)
    asyncio.run(repo.create(Composer(id="m", name="\u00d0\u00d0\u00d0\u00ba\u00d0 \u00d0\u00d0",
                                     review_status="correct")))
    asyncio.run(repo.create(Composer(id="g", name="Wolfgang Amadeus Mozart", review_status="correct")))
    result = asyncio.run(FlagMojibakeComposers(repo).execute())
    assert result["flagged"] == 1
    assert asyncio.run(repo.get_by_id("m")).review_status == "incorrect"
    assert asyncio.run(repo.get_by_id("g")).review_status == "correct"


def test_classifier_clean_name_correct():
    assert classify_composer_name("Wolfgang Amadeus Mozart") == REVIEW_CORRECT
    assert classify_composer_name("Bach, Johann Sebastian") == REVIEW_CORRECT
    assert is_suspicious("Wolfgang Amadeus Mozart") is False


def test_classifier_noise_incorrect():
    assert classify_composer_name("76") == REVIEW_INCORRECT
    assert classify_composer_name("123456") == REVIEW_INCORRECT
    assert classify_composer_name("Claude Debussy arr. Andrew Hearn") == REVIEW_INCORRECT
    assert classify_composer_name("Claude Debussy [arranged from]") == REVIEW_INCORRECT
    assert classify_composer_name("Attr. to William Bird") == REVIEW_INCORRECT
    assert classify_composer_name("Tune is A Gigg by William Bird") == REVIEW_INCORRECT
    assert classify_composer_name("Stetsenko (1882-1922)") == REVIEW_INCORRECT
    assert classify_composer_name("By Mr Clark") == REVIEW_INCORRECT
    assert classify_composer_name("L blanke arr OKNEM") == REVIEW_INCORRECT
    assert classify_composer_name("Original music by John Welsman") == REVIEW_INCORRECT


def test_classifier_ambiguous_not_reviewed():
    assert classify_composer_name("Mozart") == REVIEW_NOT_REVIEWED  # una sola palabra
    assert classify_composer_name("Stetsenko") == REVIEW_NOT_REVIEWED


def test_review_composer_sets_status():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="a", name="Johann Sebastian Bach")))
    detail = asyncio.run(ReviewComposer(repo).execute("a", "correct"))
    assert detail.review_status == "correct"
    assert asyncio.run(repo.get_by_id("a")).review_status == "correct"


def test_review_invalid_status_rejected():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="a", name="Bach")))
    with pytest.raises(ValueError):
        asyncio.run(ReviewComposer(repo).execute("a", "maybe"))


def test_review_missing_404():
    repo = InMemoryComposerRepository()
    with pytest.raises(EntityNotFound):
        asyncio.run(ReviewComposer(repo).execute("nope", "correct"))


def test_classify_pending_composers():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="good", name="Ludwig van Beethoven")))
    asyncio.run(repo.create(Composer(id="bad", name="Claude Debussy arr. Andrew Hearn")))
    asyncio.run(repo.create(Composer(id="digits", name="99")))
    result = asyncio.run(ClassifyComposers(repo).execute())
    assert result[REVIEW_CORRECT] == 1
    assert result[REVIEW_INCORRECT] == 2
    assert asyncio.run(repo.get_by_id("good")).review_status == "correct"
    assert asyncio.run(repo.get_by_id("bad")).review_status == "incorrect"
    assert asyncio.run(repo.get_by_id("digits")).review_status == "incorrect"


def test_classify_no_skip_on_pagination():
    # Regresión: con un limit pequeño, clasificar no debe saltarse compositores
    # (el conjunto not_reviewed se reduce y el offset se desplaza).
    repo = InMemoryComposerRepository()
    names = [f"Nombre De Prueba {chr(65+i)} Xyz" for i in range(6)]  # todos correctos
    for i, n in enumerate(names):
        asyncio.run(repo.create(Composer(id=f"c{i}", name=n)))
    result = asyncio.run(ClassifyComposers(repo).execute(limit=2))
    assert result[REVIEW_CORRECT] == 6
    assert result[REVIEW_INCORRECT] == 0
    for i in range(6):
        assert asyncio.run(repo.get_by_id(f"c{i}")).review_status == "correct"


def test_list_filter_by_review():
    repo = InMemoryComposerRepository()
    asyncio.run(repo.create(Composer(id="a", name="Clean Name", review_status="correct")))
    asyncio.run(repo.create(Composer(id="b", name="Noise arr. X", review_status="incorrect")))
    result = asyncio.run(ListComposers(repo).execute(limit=50, offset=0, review="correct"))
    assert result.total == 1
    assert result.items[0].id == "a"
    bad = asyncio.run(ListComposers(repo).execute(limit=50, offset=0, review="incorrect"))
    assert bad.total == 1
    assert bad.items[0].id == "b"
