import pytest
from domain.entities.resource import Resource, ResourceKind, ResourceVisibility


def test_url_only_reference_is_valid():
    resource = Resource(
        work_id=1,
        kind=ResourceKind.REFERENCE,
        external_url="https://www.cpdl.org/wiki/index.php?curid=7994",
        is_reference=True,
    )
    assert resource.is_reference is True
    assert resource.visibility is ResourceVisibility.PUBLIC


def test_reference_kind_marks_reference():
    assert Resource(work_id=1, kind=ResourceKind.REFERENCE).is_reference is True


def test_work_id_must_be_positive():
    with pytest.raises(ValueError):
        Resource(work_id=0)


def test_metadata_is_not_shared_between_resources():
    first = Resource(work_id=1)
    second = Resource(work_id=1)
    first.metadata["key"] = "C major"
    assert second.metadata == {}


def test_resource_describes_its_own_license_and_source():
    resource = Resource(
        work_id=2,
        kind=ResourceKind.SCORE,
        source_system="cpdl",
        external_id="7994:11784",
        license="Licencia CPDL",
    )
    assert resource.source_system == "cpdl"
    assert resource.external_id == "7994:11784"
    assert resource.license == "Licencia CPDL"
