from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.billing import (
    ChargeRequest,
    ChargeResponse,
    PlanType,
    TopUpRequest,
    WalletBalance,
)
from app.services.billing import BillingService, InsufficientFundsError, WalletNotFoundError


# In-memory репозиторий для изоляции и быстрого запуска стенда
class InMemoryBillingRepository:
    def __init__(self) -> None:
        self.wallets: dict[int, WalletBalance] = {}
        self.transactions: dict[str, dict[str, Any]] = {}

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
        self, user_id: int, amount: int, transaction_id: str, status: str
    ) -> bool:
        wallet = self.wallets.get(user_id)
        rem = wallet.balance if wallet else 0
        self.transactions[transaction_id] = {
            "user_id": user_id,
            "amount": amount,
            "status": status,
            "remaining_balance": rem,
        }
        return True

    async def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        return self.transactions.get(transaction_id)


# Синглтон репозитория для учебного контура
_repo_instance = InMemoryBillingRepository()


def get_billing_service() -> BillingService:
    return BillingService(repo=_repo_instance)


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
        )
    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)) from e
    except WalletNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
