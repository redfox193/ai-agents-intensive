"""Юнит-тесты контрактов квоты плана FREE (REQ-EARS-07 / REQ-BILL-09, Волна 1)."""

import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.billing import (
    FREE_LINK_LIMIT,
    PlanQuotaInfo,
    PlanType,
    QuotaExceededResponse,
)
from app.services.billing import (
    BillingError,
    BillingService,
    QuotaExceededError,
    WalletNotFoundError,
)


def test_free_link_limit_constant() -> None:
    assert FREE_LINK_LIMIT == 10


def test_plan_quota_info_free_valid() -> None:
    info = PlanQuotaInfo(
        user_id=1, plan=PlanType.FREE, active_links=FREE_LINK_LIMIT, limit=FREE_LINK_LIMIT
    )
    assert info.plan is PlanType.FREE
    assert info.limit == 10
    # Точка отказа сервисного слоя: на лимите ссылка уже не создаётся.
    expected_exceeded = info.active_links >= info.limit > 0
    assert expected_exceeded is True
    info_ok = PlanQuotaInfo(
        user_id=1,
        plan=PlanType.FREE,
        active_links=FREE_LINK_LIMIT - 1,
        limit=FREE_LINK_LIMIT,
        exceeded=False,
    )
    assert info_ok.active_links < info_ok.limit
    assert info_ok.exceeded is False


def test_plan_quota_info_exceeded_flag() -> None:
    info = PlanQuotaInfo(
        user_id=2,
        plan=PlanType.FREE,
        active_links=11,
        limit=FREE_LINK_LIMIT,
        exceeded=True,
    )
    assert info.exceeded is True
    assert info.active_links == 11


def test_plan_quota_info_pro_no_limit_semantics() -> None:
    """PRO/ENTERPRISE не трогаются лимитом FREE (REQ-BILL-09)."""
    info = PlanQuotaInfo(
        user_id=3,
        plan=PlanType.PRO,
        active_links=999,
        limit=0,  # 0 = лимит не применяется (без лимита)
        exceeded=False,
    )
    assert info.plan is PlanType.PRO
    assert info.limit == 0


def test_plan_quota_info_negative_active_links_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanQuotaInfo(user_id=1, plan=PlanType.FREE, active_links=-1)


def test_plan_quota_info_invalid_plan_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanQuotaInfo(user_id=1, plan="GOLD")  # type: ignore[arg-type]


def test_quota_exceeded_response_dto() -> None:
    resp = QuotaExceededResponse(
        plan=PlanType.FREE, limit=FREE_LINK_LIMIT, active_links=10
    )
    assert resp.detail == "Free plan link quota exceeded"
    assert resp.plan is PlanType.FREE
    assert resp.limit == 10
    assert resp.active_links == 10


def test_quota_exceeded_response_custom_detail() -> None:
    resp = QuotaExceededResponse(
        detail="Free plan allows only 10 active links",
        plan=PlanType.FREE,
        limit=10,
        active_links=11,
    )
    assert resp.detail == "Free plan allows only 10 active links"
    assert resp.active_links == 11


# ----------------------------------------------------------------------
# Волна 3 (REQ-BILL-09): сервис квоты BillingService (red→green)
# ----------------------------------------------------------------------


class FakeQuotaRepo:
    """Fake-репозиторий протокола: трассировка вызовов для тестов атомарности."""

    def __init__(self, wallets: dict[int, SimpleNamespace], active: dict[int, int]) -> None:
        self._wallets = wallets
        self._active = active
        self.register_calls: list[int] = []
        self.release_calls: list[int] = []
        self.count_calls = 0

    async def get_wallet(self, user_id: int) -> SimpleNamespace | None:
        return self._wallets.get(user_id)

    async def update_balance(self, user_id: int, new_balance: int) -> bool:
        return True

    async def record_transaction(self, **kwargs: object) -> bool:
        return True

    async def get_transaction(self, transaction_id: str) -> dict[str, object] | None:
        return None

    async def list_transactions(self, user_id: int) -> list[dict[str, object]]:
        return []

    async def count_active_links(self, user_id: int) -> int:
        self.count_calls += 1
        return self._active.get(user_id, 0)

    async def register_new_link(self, user_id: int) -> bool:
        self.register_calls.append(user_id)
        self._active[user_id] = self._active.get(user_id, 0) + 1
        return True

    async def release_link(self, user_id: int) -> bool:
        self.release_calls.append(user_id)
        before = self._active.get(user_id, 0)
        self._active[user_id] = max(0, before - 1)
        return before > 0


def _service_free(active: int = 0) -> tuple[BillingService, FakeQuotaRepo]:
    repo = FakeQuotaRepo(
        wallets={1: SimpleNamespace(plan=PlanType.FREE)}, active={1: active}
    )
    return BillingService(repo=repo), repo  # type: ignore[arg-type]


def _paid_service(plan: PlanType, active: int) -> tuple[BillingService, FakeQuotaRepo]:
    repo = FakeQuotaRepo(wallets={2: SimpleNamespace(plan=plan)}, active={2: active})
    return BillingService(repo=repo), repo  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_link_quota_free_limit() -> None:
    svc, repo = _service_free(active=FREE_LINK_LIMIT - 1)
    info = await svc.get_link_quota(1)
    assert info.user_id == 1
    assert info.plan is PlanType.FREE
    assert info.limit == FREE_LINK_LIMIT
    assert info.active_links == FREE_LINK_LIMIT - 1
    assert info.exceeded is False
    assert repo.count_calls == 1
    assert repo.register_calls == []


@pytest.mark.asyncio
async def test_get_link_quota_wallet_not_found() -> None:
    svc, repo = _service_free()
    with pytest.raises(WalletNotFoundError):
        await svc.get_link_quota(999)
    assert repo.count_calls == 0


@pytest.mark.asyncio
async def test_free_10_links_ok_then_11th_exceeded() -> None:
    svc, repo = _service_free(active=0)
    for created in range(FREE_LINK_LIMIT):
        info = await svc.register_link_creation(1)
        assert info.active_links == created + 1
        # До лимита квота не исчерпана; ровно на 10-й exceeded=True (создание прошло).
        assert info.exceeded is (created + 1 >= FREE_LINK_LIMIT)
    assert len(repo.register_calls) == FREE_LINK_LIMIT
    # 11-я ссылка -> QuotaExceededError, регистрация не выполняется.
    with pytest.raises(QuotaExceededError):
        await svc.register_link_creation(1)
    assert len(repo.register_calls) == FREE_LINK_LIMIT


@pytest.mark.asyncio
async def test_paid_plans_have_no_free_limit() -> None:
    for plan in (PlanType.PRO, PlanType.ENTERPRISE):
        svc, repo = _paid_service(plan, active=FREE_LINK_LIMIT + 100)
        info = await svc.get_link_quota(2)
        assert info.limit == sys.maxsize
        assert info.exceeded is False
        # Регистрация проходит даже «за» лимитом FREE.
        result = await svc.register_link_creation(2)
        assert result.active_links == FREE_LINK_LIMIT + 101
        assert repo.register_calls == [2]


@pytest.mark.asyncio
async def test_assert_link_quota_passes_before_limit() -> None:
    svc, _ = _service_free(active=FREE_LINK_LIMIT - 1)
    info = await svc.assert_link_quota(1)
    assert info.exceeded is False


@pytest.mark.asyncio
async def test_quota_error_is_domain_billing_error_with_safe_message() -> None:
    svc, _ = _service_free(active=FREE_LINK_LIMIT)
    with pytest.raises(BillingError) as exc_info:
        await svc.assert_link_quota(1)
    assert isinstance(exc_info.value, QuotaExceededError)
    # Zero Auth Leak: сообщение не содержит секретов/идентификаторов чужих данных.
    assert "Free plan link quota exceeded" in str(exc_info.value)


@pytest.mark.asyncio
async def test_release_link_recounts() -> None:
    svc, repo = _service_free(active=FREE_LINK_LIMIT)
    await svc.release_link(1)
    assert repo.release_calls == [1]
    info = await svc.get_link_quota(1)
    assert info.active_links == FREE_LINK_LIMIT - 1
    assert info.exceeded is False


@pytest.mark.asyncio
async def test_register_skips_repo_when_assert_fails() -> None:
    svc, repo = _service_free(active=FREE_LINK_LIMIT + 1)
    with pytest.raises(QuotaExceededError):
        await svc.register_link_creation(1)
    # Атомарность: при отказе assert репозиторий не вызывается.
    assert repo.register_calls == []
