import logging

import pytest

from app.services.billing import REDACTED_VALUE, WalletNotFoundError

SECRET_VALUE = "partner-secret-token-do-not-leak"


@pytest.mark.asyncio
async def test_charge_audit_after_charges(service):
    await service.charge_click(
        user_id=1,
        link_id=10,
        amount=100,
        transaction_id="tx_audit_first_0001",
        partner_metadata={"campaign": "spring", "partner_ref": "p-123"},
    )
    await service.charge_click(
        user_id=1,
        link_id=11,
        amount=50,
        transaction_id="tx_audit_second_0002",
    )
    audit = await service.get_charge_audit(user_id=1)

    assert audit.user_id == 1
    assert audit.total_charges == 2
    assert len(audit.entries) == 2
    first, second = audit.entries
    assert first.transaction_id == "tx_audit_first_0001"
    assert first.amount == 100
    assert first.status == "SUCCESS"
    assert first.remaining_balance == 900
    # Значения метаданных маскируются (Zero Auth Leak, инвариант 5)
    assert first.partner_metadata == {"campaign": "***", "partner_ref": "***"}
    assert set(first.redacted_keys) == {"campaign", "partner_ref"}
    assert second.amount == 50
    assert second.remaining_balance == 850


@pytest.mark.asyncio
async def test_charge_audit_created_at_is_datetime(service):
    await service.charge_click(
        user_id=1,
        link_id=10,
        amount=25,
        transaction_id="tx_audit_created_at_0004",
    )
    audit = await service.get_charge_audit(user_id=1)
    assert audit.entries[0].created_at is not None


@pytest.mark.asyncio
async def test_charge_audit_wallet_not_found(service):
    with pytest.raises(WalletNotFoundError):
        await service.get_charge_audit(user_id=999)


@pytest.mark.asyncio
async def test_charge_audit_zero_auth_leak(service, caplog):
    caplog.set_level(logging.DEBUG, logger="app.services.billing")
    await service.charge_click(
        user_id=1,
        link_id=10,
        amount=25,
        transaction_id="tx_audit_secret_0003",
        partner_metadata={"auth_token": SECRET_VALUE},
    )
    audit = await service.get_charge_audit(user_id=1)
    # Zero Auth Leak (инвариант 5): сырые значения partner_metadata не покидают журнал
    assert audit.model_dump(mode="json")["entries"][0]["partner_metadata"] == {
        "auth_token": REDACTED_VALUE
    }
    assert audit.model_dump()["entries"][0]["partner_metadata"]["auth_token"] == "***"
    assert SECRET_VALUE not in audit.model_dump_json()
    assert SECRET_VALUE not in str(audit)
    # Ключи же помечаются как скрытые — контракт redacted_keys
    assert audit.entries[0].redacted_keys == ["auth_token"]
    # Секрет не попал в логи (Zero Auth Leak, CWE-532)
    leaked_logs = [r.getMessage() for r in caplog.records if SECRET_VALUE in r.getMessage()]
    assert leaked_logs == []


@pytest.mark.asyncio
async def test_charge_click_error_message_no_secret(service, caplog):
    caplog.set_level(logging.DEBUG, logger="app.services.billing")
    with pytest.raises(WalletNotFoundError) as exc_info:
        await service.get_charge_audit(user_id=999)
    # Сообщение исключения не содержит секретов из partner_metadata
    assert SECRET_VALUE not in str(exc_info.value)
    leaked_logs = [r.getMessage() for r in caplog.records if SECRET_VALUE in r.getMessage()]
    assert leaked_logs == []


@pytest.mark.asyncio
async def test_charge_click_idempotency_same_owner_returns_original_balance(service):
    first = await service.charge_click(
        user_id=1, link_id=10, amount=100, transaction_id="tx_idem_owner_0005"
    )
    assert first.remaining_balance == 900

    retry = await service.charge_click(
        user_id=1, link_id=10, amount=100, transaction_id="tx_idem_owner_0005"
    )
    assert retry.success is True
    assert retry.remaining_balance == 900


@pytest.mark.asyncio
async def test_charge_click_idempotency_cross_user_no_foreign_balance(service):
    first = await service.charge_click(
        user_id=1, link_id=10, amount=100, transaction_id="tx_idem_cowner_0006"
    )
    assert first.remaining_balance == 900

    # Другой пользователь переиспользует чужой transaction_id
    from app.schemas.billing import PlanType, WalletBalance

    service.repo.wallets[2] = WalletBalance(user_id=2, balance=500, plan=PlanType.FREE)
    second = await service.charge_click(
        user_id=2, link_id=10, amount=100, transaction_id="tx_idem_cowner_0006"
    )
    # Чужой remaining_balance никогда не возвращается; ответ нейтральный
    assert second.success is True
    assert second.remaining_balance == 500
    assert second.remaining_balance != first.remaining_balance


@pytest.mark.asyncio
async def test_charge_audit_namespace_isolated_per_user(service):
    """RW-005: аудит возвращает только данные владельца журнала.

    Ограничение учебного контура (см. docs/domains/billing.md): auth-субъекта
    запроса нет, cross-user чтение на эндпоинте не запрещено инфраструктурой.
    Гарантия жёстче уровня эндпоинта — изоляция данных по владельцу в журнале:
    чужие записи не попадают в ответ аудита при любом запрошенном user_id.
    """
    await service.charge_click(
        user_id=1, link_id=10, amount=100, transaction_id="tx_owner_a_0007"
    )
    audit_user1 = await service.get_charge_audit(user_id=1)
    assert all(entry.user_id == 1 for entry in audit_user1.entries)
