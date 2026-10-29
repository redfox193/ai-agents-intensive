from typing import Any, Protocol, runtime_checkable

from app.schemas.billing import WalletBalance


@runtime_checkable
class BillingRepositoryProtocol(Protocol):
    """Контракт хранилища данных биллинга (PEP 544)."""

    async def get_wallet(self, user_id: int) -> WalletBalance | None:
        """Получить информацию о балансе пользователя."""
        ...

    async def update_balance(self, user_id: int, new_balance: int) -> bool:
        """Атомарно обновить баланс пользователя."""
        ...

    async def record_transaction(
        self,
        user_id: int,
        amount: int,
        transaction_id: str,
        status: str,
        partner_metadata: dict[str, str] | None = None,
    ) -> bool:
        """Зафиксировать транзакцию в журнале (метаданные не логируются — Zero Auth Leak)."""
        ...

    async def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        """Проверить статус транзакции для обеспечения идемпотентности."""
        ...

    async def list_transactions(self, user_id: int) -> list[dict[str, Any]]:
        """Вернуть сохранённые транзакции пользователя (для аудита списаний)."""
        ...

    async def count_active_links(self, user_id: int) -> int:
        """Число активных ссылок владельца в контуре (для квоты плана FREE)."""
        ...

    async def register_new_link(self, user_id: int) -> bool:
        """Зафиксировать создание активной ссылки владельцем.

        Возвращает ``True``, если ссылка принята на учёт.
        """
        ...

    async def release_link(self, user_id: int) -> bool:
        """Снять активную ссылку владельца с учёта (disable).

        Возвращает ``True``, если ссылка была на учёте и снята.
        """
        ...


class PaymentGatewayProtocol(Protocol):
    """Контракт внешнего платежного шлюза."""

    async def process_external_charge(self, token: str, amount: int) -> str:
        """Инициировать списание через сторонний провайдер (Stripe/Банк)."""
        ...
