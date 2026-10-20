#!/usr/bin/env python3
import subprocess
import sys


def run_step(step_num, title, cmd):
    print(f"\n[{step_num}/5] >>> {title}...")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ ПРОВЕРКА [{title}] ПРОВАЛЕНА (код {res.returncode}):")
        print(res.stdout)
        print(res.stderr)
        return False
    print(f"✅ [{title}] УСПЕШНО ПРОЙДЕНА")
    return True


def verify_techlead_gate():
    print("=" * 70)
    print("      КОНТРОЛЬНЫЙ ШЛЮЗ ТИМЛИДА (TECHLEAD GATE: 5 СТУПЕНЕЙ)")
    print("=" * 70)

    steps = [
        (1, "Синхронизация Базы Знаний", "python3 tools/verify_kb_sync.py"),
        (
            2,
            "Ацикличность графа зависимостей AST",
            "python3 tools/build_dependency_graph.py --check-cycles",
        ),
        (3, "Соблюдение границ архитектурных слоев", "python3 tools/verify_architecture_layers.py"),
        (
            4,
            "Бюджет зоны поражения (Blast Radius <= 7 файлов)",
            "python3 tools/verify_blast_radius.py",
        ),
        (5, "Полный регрессионный тест-сьют (pytest)", "pytest tests/unit tests/integration -q"),
    ]

    for num, title, cmd in steps:
        if not run_step(num, title, cmd):
            print("\n" + "=" * 70)
            print("🚨 СТАТУС ПРИЁМКИ: ОТКЛОНЕНО ТИМЛИДОМ (TECHLEAD GATE: REJECTED)")
            print("=" * 70)
            return 1

    print("\n" + "=" * 70)
    print("🏆 СТАТУС ПРИЁМКИ: ОДОБРЕНО ТИМЛИДОМ (TECHLEAD GATE: ACCEPTED)")
    print("   Все 5 ступеней проверок пройдены со 100% результатом!")
    print("   Код допущен к объединению с основной веткой (Ready to Merge).")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(verify_techlead_gate())
