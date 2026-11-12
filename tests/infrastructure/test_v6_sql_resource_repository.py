import json

from domain.entities.resource import ResourceKind, ResourceVisibility
from infrastructure.repositories.sql_resource_repository import _row_to_resource


def _row(**overrides):
    base = {
        "id": 7,
        "work_id": 287062,
        "kind": "score",
        "title": "Ave verum",
        "source_system": "cpdl",
        "external_id": "7994:11784",
        "external_url": "https://www.cpdl.org/wiki/index.php?curid=7994",
        "license": "Licencia CPDL",
        "rights_holder": None,
        "is_reference": 0,
        "visibility": "public",
        "metadata_json": json.dumps({"key": "C major"}),
        "created_by": None,
        "created_at": None,
        "updated_at": None,
    }
    base.update(overrides)
    return base


def test_row_maps_v6_resource_and_json_metadata():
    resource = _row_to_resource(_row())
    assert resource.id == 7
    assert resource.work_id == 287062
    assert resource.kind is ResourceKind.SCORE
    assert resource.visibility is ResourceVisibility.PUBLIC
    assert resource.metadata == {"key": "C major"}
    assert resource.is_reference is False
    assert resource.external_url.endswith("curid=7994")


def test_row_accepts_dict_metadata_and_reference_flag():
    resource = _row_to_resource(
        _row(kind="reference", is_reference=1, metadata_json={"voices": ["SATB"]})
    )
    assert resource.kind is ResourceKind.REFERENCE
    assert resource.is_reference is True
    assert resource.metadata == {"voices": ["SATB"]}


def test_row_with_invalid_metadata_falls_back_to_empty_dict():
    resource = _row_to_resource(_row(metadata_json="{not-json"))
    assert resource.metadata == {}
