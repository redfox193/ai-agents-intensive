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


class ChargeResponse(BaseModel):
    success: bool
    transaction_id: str
    remaining_balance: int
    message: str
