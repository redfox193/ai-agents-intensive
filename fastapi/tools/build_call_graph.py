#!/usr/bin/env python3
import ast
from collections import defaultdict
from pathlib import Path


class CallVisitor(ast.NodeVisitor):
    def __init__(self, current_module):
        self.current_module = current_module
        self.current_func = None
        self.calls = defaultdict(set)

    def visit_FunctionDef(self, node):
        prev = self.current_func
        self.current_func = f"{self.current_module}:{node.name}"
        self.generic_visit(node)
        self.current_func = prev

    def visit_AsyncFunctionDef(self, node):
        prev = self.current_func
        self.current_func = f"{self.current_module}:{node.name}"
        self.generic_visit(node)
        self.current_func = prev

    def visit_Call(self, node):
        if self.current_func:
            if isinstance(node.func, ast.Name):
                self.calls[self.current_func].add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                self.calls[self.current_func].add(node.func.attr)
        self.generic_visit(node)


def build_call_graph(root_dir: Path):
    app_dir = root_dir / "app"
    all_calls = defaultdict(set)

    for py_file in app_dir.rglob("*.py"):
        rel = py_file.relative_to(root_dir)
        mod = str(rel).replace("/", ".").replace(".py", "")
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            visitor = CallVisitor(mod)
            visitor.visit(tree)
            for caller, callees in visitor.calls.items():
                all_calls[caller].update(callees)
        except Exception:
            pass
    return all_calls


def main():
    root = Path.cwd()
    graph = build_call_graph(root)
    print("=== ГРАФ ВЫЗОВОВ ФУНКЦИЙ МОНОЛИТА (CALL GRAPH) ===")
    for caller, callees in sorted(graph.items()):
        relevant = [c for c in callees if not c.startswith("_")]
        if relevant:
            print(f"{caller} -> {', '.join(sorted(relevant)[:5])}")


if __name__ == "__main__":
    main()
