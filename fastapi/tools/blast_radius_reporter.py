#!/usr/bin/env python3
import subprocess
import sys


def generate_report():
    res = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True)
    lines = res.stdout.splitlines()

    print("=== ОТЧЕТ О ЗОНЕ ВЛИЯНИЯ ИЗМЕНЕНИЙ (BLAST RADIUS AUDIT) ===")
    if not lines:
        print("Изменения отсутствуют (рабочая директория чиста).")
        return 0

    print("Измененные файлы и строки:")
    for line in lines:
        print(f"   {line}")

    # Проверяем бюджет
    status_code = subprocess.run(["python3", "tools/verify_blast_radius.py"]).returncode
    if status_code == 0:
        print("\n✅ ВЕРДИКТ: Бюджет соблюден. Задача допущена к объединению.")
        return 0
    else:
        print("\n🚨 ВЕРДИКТ: ПРЕВЫШЕН БЮДЖЕТ BLAST RADIUS! Слияние заблокировано.")
        return 1


if __name__ == "__main__":
    sys.exit(generate_report())
