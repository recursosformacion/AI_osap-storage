from __future__ import annotations

from domain.entities.file import File, FileStatus
from domain.entities.storage_location import LocationStatus, StorageLocation
from domain.services.availability import AvailabilityService

SHA = "a" * 64


def _file(status: FileStatus = FileStatus.AVAILABLE) -> File:
    return File(sha256=SHA, name="x.txt", status=status, id=1)


def _stored_location() -> StorageLocation:
    return StorageLocation(
        file_id=1,
        provider_id=1,
        object_key="aa/aaa",
        status=LocationStatus.STORED,
        id=1,
    )


def test_available_with_stored_location():
    result = AvailabilityService().availability(_file(), [_stored_location()])
    assert result.available
    assert len(result.stored_locations) == 1


def test_not_available_without_locations():
    result = AvailabilityService().availability(_file(), [])
    assert not result.available


def test_failed_file_is_not_available_even_with_location():
    result = AvailabilityService().availability(_file(FileStatus.FAILED), [_stored_location()])
    assert not result.available


def test_only_stored_locations_count_as_stored():
    failed_location = StorageLocation(
        file_id=1,
        provider_id=1,
        object_key="aa/aaa",
        status=LocationStatus.FAILED,
        id=2,
    )
    result = AvailabilityService().availability(_file(), [failed_location])
    assert not result.available
