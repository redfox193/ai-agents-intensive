#!/usr/bin/env python3
import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path


class DependencyVisitor(ast.NodeVisitor):
    def __init__(self, current_module):
        self.current_module = current_module
        self.imports = set()

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name.startswith("app"):
                self.imports.add(alias.name)

    def visit_ImportFrom(self, node):
        if node.module and node.module.startswith("app"):
            self.imports.add(node.module)
        elif node.level > 0:  # Относительный импорт (from . import ...)
            # Упрощенно резолвим в рамках app
            self.imports.add(f"relative_level_{node.level}")


def build_graph(root_dir: Path):
    graph = defaultdict(set)
    app_dir = root_dir / "app"

    if not app_dir.exists():
        return graph

    for py_file in app_dir.rglob("*.py"):
        rel_path = py_file.relative_to(root_dir)
        module_name = str(rel_path).replace("/", ".").replace(".py", "")
        if module_name.endswith(".__init__"):
            module_name = module_name[:-9]

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            visitor = DependencyVisitor(module_name)
            visitor.visit(tree)

            # Сохраняем зависимости
            for imp in visitor.imports:
                graph[module_name].add(imp)
        except Exception as e:
            print(f"Предупреждение: не удалось распарсить {py_file}: {e}", file=sys.stderr)

    return graph


def find_cycles_tarjan(graph):
    index = 0
    indices = {}
    lowlink = {}
    on_stack = set()
    stack = []
    sccs = []

    def strongconnect(node):
        nonlocal index
        indices[node] = index
        lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in graph.get(node, []):
            if neighbor not in indices:
                strongconnect(neighbor)
                lowlink[node] = min(lowlink[node], lowlink[neighbor])
            elif neighbor in on_stack:
                lowlink[node] = min(lowlink[node], indices[neighbor])

        if lowlink[node] == indices[node]:
            scc = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == node:
                    break
            if len(scc) > 1:
                sccs.append(scc)

    for node in list(graph.keys()):
        if node not in indices:
            strongconnect(node)

    return sccs


def main():
    parser = argparse.ArgumentParser(description="Анализатор AST-графа зависимостей монолита")
    parser.add_argument(
        "--check-cycles", action="store_true", help="Проверить наличие циклических импортов"
    )
    parser.add_argument("--target", type=str, help="Модуль для точечного Scoped Retrieval")
    parser.add_argument(
        "--format", choices=["text", "json", "mermaid"], default="text", help="Формат вывода"
    )
    args = parser.parse_args()

    root = Path.cwd()
    graph = build_graph(root)

    if args.check_cycles:
        cycles = find_cycles_tarjan(graph)
        if cycles:
            print("❌ ОБНАРУЖЕНЫ ЦИКЛИЧЕСКИЕ ИМПОРТЫ (ЦИКЛЫ В DAG):")
            for c in cycles:
                print(f"   Цикл: {' <-> '.join(c)}")
            sys.exit(1)
        else:
            print(
                "✅ АЦИКЛИЧНОСТЬ ПОДТВЕРЖДЕНА: Монолит представляет собой чистый DAG (циклов нет)"
            )
            return

    if args.target:
        print(f"=== SCOPED RETRIEVAL ДЛЯ: {args.target} ===")
        visited = set()
        to_visit = [args.target]
        while to_visit:
            curr = to_visit.pop(0)
            if curr not in visited:
                visited.add(curr)
                deps = graph.get(curr, set())
                for d in deps:
                    if d.startswith("app"):
                        to_visit.append(d)
        print(f"Минимально необходимый контекст ({len(visited)} модулей):")
        for m in sorted(visited):
            print(f"   - {m}")
        return

    print("=== ТОПОЛОГИЯ МОНОЛИТА (МОДУЛИ И ИМПОРТЫ) ===")
    for src, targets in sorted(graph.items()):
        if targets:
            print(f"{src} -> {', '.join(sorted(targets))}")


if __name__ == "__main__":
    main()
