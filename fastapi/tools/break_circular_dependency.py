#!/usr/bin/env python3
import sys
from pathlib import Path as _Path

sys.path.insert(
    0, str(_Path(__file__).resolve().parents[1])
)  # корень проекта: импорт `app` и `tools`

import ast
import sys
from pathlib import Path

from tools.build_dependency_graph import build_graph, find_cycles_tarjan


def analyze_cycle_symbols(module_a, module_b):
    print(f"\nДетальный синтаксический анализ связи: {module_a} <-> {module_b}")
    file_a = Path(module_a.replace(".", "/") + ".py")
    file_b = Path(module_b.replace(".", "/") + ".py")

    def get_imported_symbols(src_file, target_mod):
        symbols = set()
        if not src_file.exists():
            return symbols
        tree = ast.parse(src_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == target_mod:
                for alias in node.names:
                    symbols.add(alias.name)
        return symbols

    syms_in_a = get_imported_symbols(file_a, module_b)
    syms_in_b = get_imported_symbols(file_b, module_a)

    print(f"   {module_a} импортирует из {module_b}: {', '.join(syms_in_a) or 'нет явных'}")
    print(f"   {module_b} импортирует из {module_a}: {', '.join(syms_in_b) or 'нет явных'}")
    print(
        "-> РЕШЕНИЕ: Вынесите эти символы в отдельный модуль DTO или используйте typing.Protocol!"
    )


def main():
    root = Path.cwd()
    graph = build_graph(root)
    cycles = find_cycles_tarjan(graph)

    print("=== АНАЛИЗАТОР РАЗРЫВА ЦИКЛИЧЕСКИХ ЗАВИСИМОСТЕЙ ===")
    if not cycles:
        print("✅ Циклических связей в графе не обнаружено (DAG чист).")
        return 0

    print(f"Обнаружено циклов: {len(cycles)}")
    for cycle in cycles:
        print(f"\nОбнаружен замкнутый цикл: {' -> '.join(cycle)} -> {cycle[0]}")
        for i in range(len(cycle)):
            mod_curr = cycle[i]
            mod_next = cycle[(i + 1) % len(cycle)]
            analyze_cycle_symbols(mod_curr, mod_next)


if __name__ == "__main__":
    main()
