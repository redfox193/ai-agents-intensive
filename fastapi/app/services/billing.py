import logging
import sys

from app.core.protocols import BillingRepositoryProtocol
from app.schemas.billing import (
    FREE_LINK_LIMIT,
    ChargeAuditEntry,
    ChargeAuditResponse,
    ChargeResponse,
    PlanQuotaInfo,
    PlanType,
    WalletBalance,
)

logger = logging.getLogger(__name__)

# Zero Auth Leak (инвариант 5, CWE-532): в аудите значения partner_metadata
# всегда заменяются на это значение; сырые строки остаются только в журнале.
REDACTED_VALUE = "***"


def mask_partner_metadata(
    partner_metadata: dict[str, str] | None,
) -> tuple[dict[str, str], list[str]]:
    """Замаскировать все значения partner_metadata (Tuple: (masked, redacted_keys))."""
    data = dict(partner_metadata or {})
    redacted_keys = sorted(key for key, value in data.items() if value != REDACTED_VALUE)
    masked = {key: REDACTED_VALUE for key in data}
    return masked, redacted_keys


class BillingError(Exception):
    """Базовое исключение домена биллинга."""


class InsufficientFundsError(BillingError):
    """Исключение: недостаточно средств на балансе."""


class WalletNotFoundError(BillingError):
    """Исключение: кошелек пользователя не найден."""


class QuotaExceededError(BillingError):
    """Исключение: превышена квота активных ссылок плана FREE.

    Сообщение не содержит секретов и счётчиков других пользователей
    (Zero Auth Leak, CWE-532).
    """


class BillingService:
    def __init__(self, repo: BillingRepositoryProtocol) -> None:
        self.repo = repo

    async def top_up(self, user_id: int, amount: int) -> WalletBalance:
        wallet = await self.repo.get_wallet(user_id)
        if not wallet:
            # Создаем кошелек по умолчанию
            new_balance = amount
            wallet = WalletBalance(user_id=user_id, balance=new_balance, plan=PlanType.FREE)
        else:
            new_balance = wallet.balance + amount
            wallet.balance = new_balance

        await self.repo.update_balance(user_id, new_balance)
        return wallet

    async def charge_click(
        self,
        user_id: int,
        link_id: int,
        amount: int,
        transaction_id: str,
        partner_metadata: dict[str, str] | None = None,
    ) -> ChargeResponse:
        # 1. Проверка идемпотентности
        existing_tx = await self.repo.get_transaction(transaction_id)
        if existing_tx:
            # Идемпотентность изолируется по владельцу: transaction_id не может
            # вернуть remaining_balance другого пользователя.
            if existing_tx.get("user_id") != user_id:
                logger.info("Идемпотентность: конфликт владельца transaction_id")
                caller_wallet = await self.repo.get_wallet(user_id)
                remaining = caller_wallet.balance if caller_wallet else 0
                return ChargeResponse(
                    success=True,
                    transaction_id=transaction_id,
                    remaining_balance=remaining,
                    message="Транзакция с данным идентификатором уже была обработана",
                )
            logger.info("Повторная транзакция идемпотентности: %s", transaction_id)
            return ChargeResponse(
                success=True,
                transaction_id=transaction_id,
                remaining_balance=existing_tx.get("remaining_balance", 0),
                message="Идемпотентный ответ: транзакция уже была обработана",
            )

        # 2. Получение кошелька
        wallet = await self.repo.get_wallet(user_id)
        if not wallet:
            raise WalletNotFoundError(f"Кошелек пользователя {user_id} не найден")

        # 3. Проверка достаточности средств
        if wallet.balance < amount:
            raise InsufficientFundsError(
                f"Недостаточно средств: баланс {wallet.balance} коп., требуется {amount} коп."
            )

        # 4. Атомарное списание; метаданные — только в журнал, не в логи (Zero Auth Leak, CWE-532)
        new_balance = wallet.balance - amount
        await self.repo.update_balance(user_id, new_balance)
        await self.repo.record_transaction(
            user_id=user_id,
            amount=amount,
            transaction_id=transaction_id,
            status="SUCCESS",
            partner_metadata=dict(partner_metadata or {}),
        )

        return ChargeResponse(
            success=True,
            transaction_id=transaction_id,
            remaining_balance=new_balance,
            message="Средства успешно списаны",
        )

    async def get_charge_audit(self, user_id: int) -> ChargeAuditResponse:
        wallet = await self.repo.get_wallet(user_id)
        if not wallet:
            # Секреты и partner_metadata не попадают в сообщения исключений (Zero Auth Leak)
            raise WalletNotFoundError(f"Кошелек пользователя {user_id} не найден")

        transactions = await self.repo.list_transactions(user_id)
        entries = []
        for tx in transactions:
            masked_metadata, redacted_keys = mask_partner_metadata(tx.get("partner_metadata"))
            entries.append(
                ChargeAuditEntry(
                    user_id=tx.get("user_id", user_id),
                    transaction_id=tx.get("transaction_id", ""),
                    amount=tx.get("amount", 0),
                    status=tx.get("status", ""),
                    remaining_balance=tx.get("remaining_balance", 0),
                    partner_metadata=masked_metadata,
                    redacted_keys=redacted_keys,
                    created_at=tx.get("created_at"),
                )
            )
        return ChargeAuditResponse(user_id=user_id, total_charges=len(entries), entries=entries)

    # ------------------------------------------------------------------
    # Квота активных ссылок (REQ-BILL-09, план FREE = FREE_LINK_LIMIT)
    # ------------------------------------------------------------------

    async def get_link_quota(self, user_id: int) -> PlanQuotaInfo:
        """Снимок квоты активных ссылок пользователя (REQ-BILL-09).

        Нет кошелька -> WalletNotFoundError; план берётся из wallet.plan,
        для FREE лимит = FREE_LINK_LIMIT, для остальных лимит не применяется.
        """
        wallet = await self.repo.get_wallet(user_id)
        if not wallet:
            raise WalletNotFoundError(f"Кошелек пользователя {user_id} не найден")

        active_links = await self.repo.count_active_links(user_id)
        if wallet.plan == PlanType.FREE:
            limit = FREE_LINK_LIMIT
            exceeded = active_links >= limit
        else:
            # PRO/ENTERPRISE: лимит FREE не применяется (sys.maxsize = без лимита).
            limit = sys.maxsize
            exceeded = False
        return PlanQuotaInfo(
            user_id=user_id,
            plan=wallet.plan,
            active_links=active_links,
            limit=limit,
            exceeded=exceeded,
        )

    async def assert_link_quota(self, user_id: int) -> PlanQuotaInfo:
        """Проверить, что создание новой активной ссылки разрешено.

        Для FREE при exceeded выбрасывается QuotaExceededError (без секретов);
        для PRO/ENTERPRISE проверка проходит всегда.
        """
        info = await self.get_link_quota(user_id)
        if info.exceeded:
            # Zero Auth Leak: сообщение без частных данных (COUNT/ID/etc).
            raise QuotaExceededError("Free plan link quota exceeded")
        return info

    async def register_link_creation(self, user_id: int) -> PlanQuotaInfo:
        """Учет новой активной ссылки: сначала проверка квоты, затем регистрация.

        «Атомарно» на уровне сервиса: при отказе проверки repo.register_new_link
        не вызывается. Возвращает обновлённый снимок квоты.
        """
        await self.assert_link_quota(user_id)
        registered = await self.repo.register_new_link(user_id)
        if not registered:
            logger.info("Регистрация ссылки не принята на учёт: user_id=%s", user_id)
        return await self.get_link_quota(user_id)

    async def release_link(self, user_id: int) -> None:
        """Снять активную ссылку владельца с учёта (disable). Без исключений."""
        await self.repo.release_link(user_id)
