#!/usr/bin/env python3
import subprocess
import time


def run_gate_cycle():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S MSK')}] Проверка контрольного шлюза Тимлида...")
    res = subprocess.run(
        ["python3", "tools/verify_techlead_gate.py"], capture_output=True, text=True
    )
    if res.returncode == 0:
        print("✅ Techlead Gate: 100% PASS (Контур чист)")
    else:
        print("🚨 Techlead Gate: FAIL! Обнаружены нарушения:")
        for line in res.stdout.splitlines():
            if "❌" in line:
                print(f"   {line}")


def main():
    print("=== ДЕМОН НЕПРЕРЫВНОГО НАДЗОРА TECHLEAD GATE АКТИВИРОВАН ===")
    run_gate_cycle()


if __name__ == "__main__":
    main()
