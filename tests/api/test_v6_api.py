from api.routes.v6 import _file, _metadata, _resource, _work


def test_work_mapping_defaults_and_counts():
    work = _work(
        {
            "id": 7,
            "works_title": "Ave verum",
            "works_song_name": "Ave verum corpus",
            "works_catalogue": "K.618",
            "works_musical_key": "D major",
            "resource_count": 3,
        }
    )
    assert work.id == 7
    assert work.catalogue == "K.618"
    assert work.resource_count == 3


def test_resource_mapping_parses_metadata_and_flags():
    resource = _resource(
        {
            "id": 10,
            "work_id": 7,
            "kind": "score",
            "title": "CPDL edition",
            "source_system": "cpdl",
            "external_id": "7994:11784",
            "external_url": "https://www.cpdl.org/wiki/index.php?curid=7994",
            "license": "Licencia CPDL",
            "rights_holder": None,
            "is_reference": 0,
            "visibility": "public",
            "metadata_json": '{"key": "D major"}',
        }
    )
    assert resource.work_id == 7
    assert resource.metadata == {"key": "D major"}
    assert resource.is_reference is False


def test_file_mapping_never_exposes_storage_key():
    file = _file(
        {"id": 4, "name": "score.mxl", "mime_type": "application/zip", "size_bytes": 10, "status": "available"}
    )
    assert file.name == "score.mxl"
    assert "storage_key" not in file.model_dump()


def test_metadata_accepts_dict_and_rejects_invalid_json():
    assert _metadata({"a": 1}) == {"a": 1}
    assert _metadata("{not-json") is None
    assert _metadata("[]") is None
