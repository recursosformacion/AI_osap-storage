import pytest
from domain.entities.file import File


def test_object_key_uses_opaque_storage_key_without_sha():
    file = File(sha256=None, name="score.mxl", storage_key="r2/objects/abc.mxl")
    assert file.object_key() == "r2/objects/abc.mxl"


def test_object_key_falls_back_to_sha_for_legacy_files():
    sha = "a" * 64
    file = File(sha256=sha, name="legacy.mxl")
    assert file.object_key() == f"aa/{sha}"


def test_file_without_key_or_sha_cannot_resolve_object():
    with pytest.raises(ValueError):
        File(sha256=None, name="missing.mxl").object_key()


def test_file_can_belong_to_a_resource():
    file = File(sha256=None, name="score.mxl", storage_key="k", resource_id=42)
    assert file.resource_id == 42
