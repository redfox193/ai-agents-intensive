import inspect

from app.api.billing import InMemoryBillingRepository
from app.core.protocols import BillingRepositoryProtocol, PaymentGatewayProtocol
from app.services.payment_adapters import MockPaymentGateway, StripePaymentGateway


def verify_protocol_methods(protocol_cls, target_cls):
    """Универсальная проверка: реализует ли target_cls все методы protocol_cls."""
    proto_methods = [
        name
        for name, val in inspect.getmembers(protocol_cls)
        if inspect.isfunction(val) and not name.startswith("_")
    ]
    for method_name in proto_methods:
        assert hasattr(target_cls, method_name), (
            f"Класс {target_cls.__name__} НЕ реализует метод '{method_name}', требуемый {protocol_cls.__name__}!"
        )


def test_in_memory_repo_conforms_to_billing_protocol():
    """Тест: InMemoryBillingRepository полностью удовлетворяет BillingRepositoryProtocol."""
    verify_protocol_methods(BillingRepositoryProtocol, InMemoryBillingRepository)


def test_mock_gateway_conforms_to_payment_protocol():
    """Тест: MockPaymentGateway полностью удовлетворяет PaymentGatewayProtocol."""
    verify_protocol_methods(PaymentGatewayProtocol, MockPaymentGateway)


def test_stripe_gateway_conforms_to_payment_protocol():
    """Тест: StripePaymentGateway полностью удовлетворяет PaymentGatewayProtocol."""
    verify_protocol_methods(PaymentGatewayProtocol, StripePaymentGateway)
