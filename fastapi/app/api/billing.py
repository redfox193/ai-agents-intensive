from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.billing import (
    ChargeAuditResponse,
    ChargeRequest,
    ChargeResponse,
    PlanType,
    QuotaExceededResponse,
    TopUpRequest,
    WalletBalance,
)
from app.services.billing import (
    BillingService,
    InsufficientFundsError,
    QuotaExceededError,
    WalletNotFoundError,
)


# In-memory репозиторий для изоляции и быстрого запуска стенда
class InMemoryBillingRepository:
    def __init__(self) -> None:
        self.wallets: dict[int, WalletBalance] = {}
        self.transactions: dict[str, dict[str, Any]] = {}
        # Реестр активных ссылок по владельцу: учебный контур квоты плана FREE
        # (модель Link не содержит owner/user_id — миграции БД не требуются).
        self.active_links: dict[int, int] = {}

    async def get_wallet(self, user_id: int) -> WalletBalance | None:
        return self.wallets.get(user_id)

    async def update_balance(self, user_id: int, new_balance: int) -> bool:
        if user_id in self.wallets:
            self.wallets[user_id].balance = new_balance
        else:
            self.wallets[user_id] = WalletBalance(
                user_id=user_id, balance=new_balance, plan=PlanType.FREE
            )
        return True

    async def record_transaction(
        self,
        user_id: int,
        amount: int,
        transaction_id: str,
        status: str,
        partner_metadata: dict[str, str] | None = None,
    ) -> bool:
        wallet = self.wallets.get(user_id)
        rem = wallet.balance if wallet else 0
        self.transactions[transaction_id] = {
            "user_id": user_id,
            "transaction_id": transaction_id,
            "amount": amount,
            "status": status,
            "remaining_balance": rem,
            "partner_metadata": dict(partner_metadata or {}),
            "created_at": datetime.now(UTC),
        }
        return True

    async def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        return self.transactions.get(transaction_id)

    async def list_transactions(self, user_id: int) -> list[dict[str, Any]]:
        return [
            tx
            for tx in self.transactions.values()
            if tx["user_id"] == user_id
        ]

    async def count_active_links(self, user_id: int) -> int:
        """Число активных ссылок владельца в контуре."""
        return self.active_links.get(user_id, 0)

    async def register_new_link(self, user_id: int) -> bool:
        """Зафиксировать создание активной ссылки владельцем."""
        self.active_links[user_id] = self.active_links.get(user_id, 0) + 1
        return True

    async def release_link(self, user_id: int) -> bool:
        """Снять активную ссылку владельца с учёта (disable)."""
        current = self.active_links.get(user_id, 0)
        self.active_links[user_id] = max(0, current - 1)
        return current > 0


# Синглтон репозитория для учебного контура
_repo_instance = InMemoryBillingRepository()


def get_billing_service() -> BillingService:
    return BillingService(repo=_repo_instance)


BillingDep = Annotated[BillingService, Depends(get_billing_service)]


router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/wallets/top-up", response_model=WalletBalance)
async def top_up_wallet(
    payload: TopUpRequest, service: Annotated[BillingService, Depends(get_billing_service)]
) -> WalletBalance:
    return await service.top_up(payload.user_id, payload.amount)


@router.post("/charges/click", response_model=ChargeResponse)
async def charge_for_click(
    payload: ChargeRequest, service: Annotated[BillingService, Depends(get_billing_service)]
) -> ChargeResponse:
    try:
        return await service.charge_click(
            user_id=payload.user_id,
            link_id=payload.link_id,
            amount=payload.amount,
            transaction_id=payload.transaction_id,
            partner_metadata=payload.partner_metadata,
        )
    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)) from e
    except WalletNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/charges/audit/{user_id}", response_model=ChargeAuditResponse)
async def get_charge_audit(
    user_id: int, service: Annotated[BillingService, Depends(get_billing_service)]
) -> ChargeAuditResponse:
    try:
        return await service.get_charge_audit(user_id)
    except WalletNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# ------------------------------------------------------------------
# Квота активных ссылок для HTTP-контура ссылок (Волна 4, REQ-BILL-09).
# user_id не передан -> анонимная ссылка, квота не проверяется (учебный контур).
# ------------------------------------------------------------------


async def apply_link_quota_guard(service: BillingService, user_id: int | None) -> None:
    """Учесть создание активной ссылки владельцем `user_id` (до фактического создания).

    При превышении квоты FREE -> HTTP 403 с телом QuotaExceededResponse;
    неизвестный пользователь (нет кошелька) -> HTTP 404.
    """
    if user_id is None:
        return
    try:
        await service.register_link_creation(user_id)
    except QuotaExceededError as e:
        # Квота уже превышена: снимок необходим для ответа с планом/лимитом.
        info = await service.get_link_quota(user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuotaExceededResponse(
                plan=info.plan,
                limit=info.limit,
                active_links=info.active_links,
            ).model_dump(),
        ) from e
    except WalletNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


async def release_link_quota_guard(service: BillingService, user_id: int | None) -> None:
    """Снять активную ссылку владельца с учёта после disable (если пользователь известен)."""
    if user_id is None:
        return
    await service.release_link(user_id)
