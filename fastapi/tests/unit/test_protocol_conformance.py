"""Конформанс InMemoryBillingRepository протоколу биллинга (Runtimе-проверка PEP 544, Волна 2)."""

from app.api.billing import InMemoryBillingRepository
from app.core.protocols import BillingRepositoryProtocol


def test_inmemory_repository_conforms_to_billing_protocol() -> None:
    """InMemory-репозиторий структурно совместим с BillingRepositoryProtocol."""
    assert isinstance(InMemoryBillingRepository(), BillingRepositoryProtocol)


async def test_active_links_counter_protocol_methods() -> None:
    """count/register/release работают по контракту реестра активных ссылок."""
    repo: BillingRepositoryProtocol = InMemoryBillingRepository()

    assert await repo.count_active_links(1) == 0

    assert await repo.register_new_link(1) is True
    assert await repo.register_new_link(1) is True
    assert await repo.count_active_links(1) == 2

    assert await repo.release_link(1) is True
    assert await repo.count_active_links(1) == 1

    # release ниже нуля не проваливается; у владельца без ссылок — False.
    await repo.release_link(1)
    await repo.release_link(1)
    assert await repo.count_active_links(1) == 0
    assert await repo.release_link(1) is False

    # Учёт изолирован по владельцу.
    assert await repo.count_active_links(42) == 0
