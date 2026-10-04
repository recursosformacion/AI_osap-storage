from __future__ import annotations

from application.use_cases.work_admin import CreateWorkAdmin
from domain.entities.work import Work
from tests.fakes import InMemoryWorkRepository


async def test_create_work_admin_usa_repo_create() -> None:
    repo = InMemoryWorkRepository()
    detail = await CreateWorkAdmin(repo).execute(
        work=Work(title="Nueva obra", origin="user", license="CC-BY")
    )

    assert detail.work.id is not None
    assert detail.work.title == "Nueva obra"
    assert detail.work.origin == "user"
    assert detail.work.license == "CC-BY"
    assert await repo.get_by_id(detail.work.id) is not None
