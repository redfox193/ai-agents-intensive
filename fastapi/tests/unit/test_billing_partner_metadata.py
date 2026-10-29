"""Юнит-тесты расширения Data Contract списания: поле partner_metadata.

- Валидация схемы ChargeRequest (типы dict[str, str], значения по умолчанию).
- Zero Auth Leak (CWE-532): метаданные не попадают в логи и message-ответы.
"""

import logging

import pytest
from pydantic import ValidationError

from app.schemas.billing import ChargeRequest
from app.services.billing import BillingService
from tests.unit.test_billing_service import MockRepo

# --- Валидация схемы ---


def test_charge_request_partner_metadata_default_empty() -> None:
    req = ChargeRequest(
        user_id=1, link_id=10, amount=50, transaction_id="tx_metadata_default_001"
    )
    assert req.partner_metadata == {}


def test_charge_request_partner_metadata_accepts_str_dict() -> None:
    req = ChargeRequest(
        user_id=1,
        link_id=10,
        amount=50,
        transaction_id="tx_metadata_ok_00000001",
        partner_metadata={"campaign": "spring", "source": "api"},
    )
    assert req.partner_metadata == {"campaign": "spring", "source": "api"}


def test_charge_request_partner_metadata_rejects_non_str_value() -> None:
    with pytest.raises(ValidationError):
        ChargeRequest(
            user_id=1,
            link_id=10,
            amount=50,
            transaction_id="tx_metadata_bad_000001",
            partner_metadata={"attempts": 3},  # int недопустим: строго dict[str, str]
        )


# --- Приём метаданных сервисом ---


@pytest.fixture
def service() -> BillingService:
    return BillingService(repo=MockRepo())


@pytest.mark.asyncio
async def test_charge_click_accepts_partner_metadata(service) -> None:
    res = await service.charge_click(
        user_id=1,
        link_id=10,
        amount=50,
        transaction_id="tx_metadata_svc_000001",
        partner_metadata={"campaign": "spring"},
    )
    assert res.success is True
    assert res.remaining_balance == 950


@pytest.mark.asyncio
async def test_charge_click_partner_metadata_zero_auth_leak(
    service, caplog: pytest.LogCaptureFixture
) -> None:
    """Zero Auth Leak (CWE-532): секретные метаданные не попадают ни в логи, ни в message."""
    secret = "value=svc_secret_token_12345"
    with caplog.at_level(logging.DEBUG, logger="app.services.billing"):
        res = await service.charge_click(
            user_id=1,
            link_id=10,
            amount=50,
            transaction_id="tx_metadata_leak_000001",
            partner_metadata={"secret": secret},
        )

    assert res.success is True
    assert secret not in res.message
    assert secret not in caplog.text
