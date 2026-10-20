import ast

from tools.verify_architecture_layers import LayerImportVisitor


def test_linter_catches_schema_importing_service(tmp_path):
    """Тест: линтер блокирует импорт сервиса в схеме."""
    schema_file = tmp_path / "app" / "schemas" / "bad.py"
    schema_file.parent.mkdir(parents=True)
    code = "from app.services.billing import BillingService\n"
    schema_file.write_text(code, encoding="utf-8")

    tree = ast.parse(code)
    visitor = LayerImportVisitor(schema_file, tmp_path)
    visitor.visit(tree)
    assert len(visitor.violations) == 1
    assert "не может импортировать 'app.services'" in visitor.violations[0][3]


def test_linter_catches_service_importing_api_router(tmp_path):
    """Тест: линтер блокирует импорт роутера в сервисе."""
    service_file = tmp_path / "app" / "services" / "bad.py"
    service_file.parent.mkdir(parents=True)
    code = "from app.api.billing import router\n"
    service_file.write_text(code, encoding="utf-8")

    tree = ast.parse(code)
    visitor = LayerImportVisitor(service_file, tmp_path)
    visitor.visit(tree)
    assert len(visitor.violations) == 1
    assert "не может импортировать 'app.api'" in visitor.violations[0][3]


def test_linter_allows_valid_downward_imports(tmp_path):
    """Тест: легитимные нисходящие импорты (api -> services -> core -> schemas) разрешены."""
    api_file = tmp_path / "app" / "api" / "good.py"
    api_file.parent.mkdir(parents=True)
    code = (
        "from app.services.billing import BillingService\n"
        "from app.schemas.billing import ChargeRequest\n"
        "from app.core.protocols import BillingRepositoryProtocol\n"
    )
    api_file.write_text(code, encoding="utf-8")

    tree = ast.parse(code)
    visitor = LayerImportVisitor(api_file, tmp_path)
    visitor.visit(tree)
    assert len(visitor.violations) == 0
