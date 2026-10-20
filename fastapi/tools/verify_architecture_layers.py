#!/usr/bin/env python3
import ast
import sys
from pathlib import Path

# Правила: для каждого префикса источника задаем список запрещенных префиксов импорта
LAYER_RULES = {
    "app/schemas": ["app.services", "app.api", "app.core", "app.db", "fastapi"],
    "app/core": ["app.services", "app.api", "app.db"],
    "app/services": ["app.api"],
}


class LayerImportVisitor(ast.NodeVisitor):
    def __init__(self, file_path, root_dir):
        self.file_path = file_path
        self.root_dir = root_dir
        self.violations = []

        # Определяем, к какому слою принадлежит проверяемый файл
        rel_str = str(file_path.relative_to(root_dir))
        self.layer_prefix = None
        for prefix in LAYER_RULES:
            if rel_str.startswith(prefix):
                self.layer_prefix = prefix
                break

    def check_module_name(self, mod_name, line_no):
        if not self.layer_prefix or not mod_name:
            return
        banned = LAYER_RULES[self.layer_prefix]
        for b in banned:
            if mod_name == b or mod_name.startswith(f"{b}."):
                self.violations.append(
                    (
                        self.file_path,
                        line_no,
                        mod_name,
                        f"Слой '{self.layer_prefix}' не может импортировать '{b}'!",
                    )
                )

    def visit_Import(self, node):
        for alias in node.names:
            self.check_module_name(alias.name, node.lineno)

    def visit_ImportFrom(self, node):
        if node.module:
            self.check_module_name(node.module, node.lineno)


def verify_layers():
    root = Path.cwd()
    app_dir = root / "app"

    if not app_dir.exists():
        print("❌ Директория app/ не найдена!")
        return 1

    all_violations = []
    py_files = list(app_dir.rglob("*.py"))

    for py_file in py_files:
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            visitor = LayerImportVisitor(py_file, root)
            visitor.visit(tree)
            all_violations.extend(visitor.violations)
        except Exception as e:
            print(f"Предупреждение: ошибка парсинга {py_file}: {e}", file=sys.stderr)

    print("=== ПРОВЕРКА ГРАНИЦ АРХИТЕКТУРНЫХ СЛОЕВ (AST LINTER) ===")
    print(f"Проверено модулей Python: {len(py_files)}")

    if all_violations:
        print(f"❌ ОБНАРУЖЕНО НАРУШЕНИЙ ГРАНИЦ СЛОЕВ: {len(all_violations)}")
        for fpath, lno, mod, reason in all_violations:
            rel = fpath.relative_to(root)
            print(f"   - {rel}:{lno} -> импорт '{mod}' | ПРИЧИНА: {reason}")
        print("❌ СБОРКА ЗАБЛОКИРОВАНА АРХИТЕКТУРНЫМ ЛИНТЕРОМ")
        return 1

    print("✅ ВСЕ АРХИТЕКТУРНЫЕ СЛОИ СОБЛЮДЕНЫ (НЕТ ЗАПРЕЩЕННЫХ ИМПОРТОВ)")
    return 0


if __name__ == "__main__":
    sys.exit(verify_layers())
