from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PlanType(StrEnum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class WalletBalance(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int = Field(..., description="Идентификатор пользователя")
    balance: int = Field(..., ge=0, description="Баланс в копейках (целое неотрицательное число)")
    plan: PlanType = Field(default=PlanType.FREE, description="Текущий тарифный план")


class TopUpRequest(BaseModel):
    user_id: int = Field(...)
    amount: int = Field(..., gt=0, description="Сумма пополнения в копейках")


class ChargeRequest(BaseModel):
    user_id: int = Field(...)
    link_id: int = Field(...)
    amount: int = Field(..., gt=0, description="Стоимость перехода в копейках")
    transaction_id: str = Field(..., min_length=16, description="Уникальный ключ идемпотентности")
    partner_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Партнёрские метаданные транзакции (ключи и значения строго str)",
    )


class ChargeAuditEntry(BaseModel):
    user_id: int
    transaction_id: str
    amount: int
    status: str
    remaining_balance: int
    # Zero Auth Leak (инвариант 5, CWE-532): в аудите значения метаданных всегда
    # замаскированы значением '***'; исходные строки покидают журнал транзакций.
    partner_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Метаданные с замаскированными значениями ('***')",
    )
    redacted_keys: list[str] = Field(
        default_factory=list,
        description="Ключи partner_metadata, чьи исходные значения скрыты",
    )
    created_at: datetime | None = None


class ChargeAuditResponse(BaseModel):
    user_id: int
    total_charges: int
    entries: list[ChargeAuditEntry]


# [REQ-EARS-07] Лимит платных/активных ссылок для плана FREE.
# Доменная константа плана; сервис волны 3 читает её отсюда (app/domain — не тронут,
# слой schemas — слой модуля billing, минимально инвазивное размещение).
FREE_LINK_LIMIT: int = 10


class PlanQuotaInfo(BaseModel):
    """Снимок квоты платных ссылок пользователя (вход сервиса квоты, волна 3)."""

    user_id: int = Field(..., description="Идентификатор пользователя-владельца")
    plan: PlanType = Field(..., description="Текущий тарифный план")
    active_links: int = Field(..., ge=0, description="Число активных ссылок пользователя")
    limit: int = Field(
        default=FREE_LINK_LIMIT,
        ge=0,
        description="Максимум активных ссылок (для FREE = FREE_LINK_LIMIT)",
    )
    exceeded: bool = Field(
        default=False,
        description="Признак превышения квоты (active_links >= limit при её наличии)",
    )


class QuotaExceededResponse(BaseModel):
    """DTO HTTP 403 `PlanQuotaExceeded` (замыкание квоты на транспортный слой)."""

    detail: str = Field(
        default="Free plan link quota exceeded",
        description="Человекочитаемое сообщение о превышении квоты",
    )
    plan: PlanType = Field(..., description="Тарифный план пользователя")
    limit: int = Field(..., ge=0, description="Применённый лимит активных ссылок")
    active_links: int = Field(..., ge=0, description="Число активных ссылок на момент отказа")


class ChargeResponse(BaseModel):
    success: bool
    transaction_id: str
    remaining_balance: int
    message: str
