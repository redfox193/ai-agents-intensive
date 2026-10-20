import inspect

from app.api import billing as billing_api
from app.schemas import billing as billing_schemas
from app.services import billing as billing_services


def test_schemas_do_not_import_services():
    """Тест: модуль schemas не содержит ссылок на классы сервисов."""
    schema_members = [m[0] for m in inspect.getmembers(billing_schemas)]
    assert "BillingService" not in schema_members
    assert "InsufficientFundsError" not in schema_members


def test_services_do_not_import_fastapi_router():
    """Тест: сервисный слой не зависит от роутеров FastAPI."""
    service_members = [m[0] for m in inspect.getmembers(billing_services)]
    assert "APIRouter" not in service_members
    assert "router" not in service_members


def test_api_uses_dependency_injection():
    """Тест: контроллеры используют Depends для внедрения сервиса."""
    sig = inspect.signature(billing_api.charge_for_click)
    params = sig.parameters
    assert "service" in params
