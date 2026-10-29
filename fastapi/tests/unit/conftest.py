"""Общие фейки/инвариантные повторно-используемые тестовые дубли billing-домена."""

from datetime import UTC, datetime

import pytest

from app.schemas.billing import PlanType, WalletBalance
from app.services.billing import BillingService


class FakeTransactionRepo:
    """In-memory реализация BillingRepositoryProtocol (журнал транзакций без БД)."""

    def __init__(self):
        self.wallets = {
            1: WalletBalance(user_id=1, balance=1000, plan=PlanType.PRO),
        }
        self.transactions = {}

    async def get_wallet(self, user_id: int):
        return self.wallets.get(user_id)

    async def update_balance(self, user_id: int, new_balance: int):
        if user_id in self.wallets:
            self.wallets[user_id].balance = new_balance
        else:
            self.wallets[user_id] = WalletBalance(
                user_id=user_id, balance=new_balance, plan=PlanType.FREE
            )
        return True

    async def record_transaction(
        self, user_id, amount, transaction_id, status, partner_metadata=None
    ):
        self.transactions[transaction_id] = {
            "user_id": user_id,
            "transaction_id": transaction_id,
            "amount": amount,
            "status": status,
            "remaining_balance": self.wallets[user_id].balance,
            "partner_metadata": dict(partner_metadata or {}),
            "created_at": datetime.now(UTC),
        }
        return True

    async def get_transaction(self, transaction_id: str):
        return self.transactions.get(transaction_id)

    async def list_transactions(self, user_id: int):
        return [tx for tx in self.transactions.values() if tx["user_id"] == user_id]


@pytest.fixture
def fake_transaction_repo():
    return FakeTransactionRepo()


@pytest.fixture
def service(fake_transaction_repo):
    return BillingService(repo=fake_transaction_repo)
