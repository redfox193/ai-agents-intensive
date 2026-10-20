#!/usr/bin/env python3
import ast
from pathlib import Path


def extract_signatures_from_file(py_file: Path):
    signatures = []
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                signatures.append(f"  class {node.name}:")
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args_list = [a.arg for a in item.args.args if a.arg != "self"]
                        signatures.append(f"    def {item.name}({', '.join(args_list)}): ...")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args_list = [a.arg for a in node.args.args]
                signatures.append(f"  def {node.name}({', '.join(args_list)}): ...")
    except Exception:
        pass
    return signatures


def main():
    root = Path.cwd()
    app_dir = root / "app"
    print("=== REPOMAP МОНОЛИТА FASTAPI (БЮДЖЕТ: ≤6k ТОКЕНОВ) ===")
    total_lines = 0
    for py_file in sorted(app_dir.rglob("*.py")):
        rel = py_file.relative_to(root)
        sigs = extract_signatures_from_file(py_file)
        if sigs:
            print(f"File: {rel}")
            for s in sigs:
                print(s)
            print()
            total_lines += len(sigs) + 2
    print(f"Всего сигнатур извлечено: {total_lines} строк (~{int(total_lines * 4)} токенов)")


if __name__ == "__main__":
    main()
