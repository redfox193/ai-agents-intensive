#!/usr/bin/env python3
import sys
from pathlib import Path as _Path

sys.path.insert(
    0, str(_Path(__file__).resolve().parents[1])
)  # корень проекта: импорт `app` и `tools`

import subprocess
import sys
from pathlib import Path

from tools.build_dependency_graph import build_graph


def calculate_blast():
    root = Path.cwd()
    res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    changed_files = [line.strip().split()[-1] for line in res.stdout.splitlines() if line.strip()]

    if not changed_files:
        print("✅ Изменений в рабочей директории нет (Семантический Blast Radius = 0).")
        return 0

    graph = build_graph(root)
    # Инвертируем граф для поиска downstream зависимостей
    dependents = {}
    for src, targets in graph.items():
        for t in targets:
            dependents.setdefault(t, set()).add(src)

    print("=== РАСЧЕТ СЕМАНТИЧЕСКОГО РАДИУСА ПОРАЖЕНИЯ (BLAST RADIUS) ===")
    total_impacted = set()
    for f in changed_files:
        mod = f.replace("/", ".").replace(".py", "")
        downstream = dependents.get(mod, set())
        total_impacted.update(downstream)
        print(f"Файл: {f} -> Прямых зависимых модулей: {len(downstream)}")
        for d in sorted(downstream):
            print(f"   [!] Затронут: {d}")

    print(f"\nИТОГО СЕМАНТИЧЕСКИЙ РАДИУС: {len(total_impacted)} модулей под риском регрессии")
    if len(total_impacted) > 10:
        print(
            "⚠️ ВНИМАНИЕ: Высокий семантический радиус! Требуется запуск полного регрессионного сьюта."
        )
    return 0


if __name__ == "__main__":
    calculate_blast()
