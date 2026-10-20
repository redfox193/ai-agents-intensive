#!/usr/bin/env python3
import re
import sys
from pathlib import Path

VALID_STATES = {"DISCUSS", "PLAN", "EXECUTE", "VERIFY", "DONE"}


def check_plan():
    root = Path.cwd()
    state_file = root / ".planning" / "STATE.md"
    roadmap_file = root / ".planning" / "ROADMAP.md"
    req_file = root / ".planning" / "REQUIREMENTS.md"

    if not state_file.exists() or not roadmap_file.exists() or not req_file.exists():
        print(
            "❌ ОШИБКА: Каталог .planning/ не инициализирован (отсутствуют обязательные артефакты)!"
        )
        return 1

    state_text = state_file.read_text(encoding="utf-8")
    m_state = re.search(r"Active State:(?:\*\*)?\s*(\w+)", state_text)
    if not m_state or m_state.group(1) not in VALID_STATES:
        print(
            f"❌ ОШИБКА: Недопустимое состояние FSM в STATE.md: {m_state.group(1) if m_state else 'None'}"
        )
        return 1

    current_state = m_state.group(1)

    m_retry = re.search(r"Retry Count:(?:\*\*)?\s*(\d+)\s*/\s*(\d+)", state_text)
    if m_retry:
        retries, max_retries = int(m_retry.group(1)), int(m_retry.group(2))
        if retries > max_retries:
            print(
                f"❌ КРИТИЧЕСКИЙ ДРЕЙФ: Превышен лимит попыток автоисправления ({retries}/{max_retries})!"
            )
            print("   Требуется возврат на фазу PLAN и пересмотр архитектуры!")
            return 2

    roadmap_text = roadmap_file.read_text(encoding="utf-8")
    waves = re.findall(r"- \[([ xX])\] \*\*([^*]+)\*\*", roadmap_text)

    print("=== ВАЛИДАЦИЯ ПЛАНА GSD-КОНВЕЙЕРА ===")
    print(f"Текущее состояние FSM: {current_state} -> OK")
    print(f"Зарегистрировано волн в ROADMAP.md: {len(waves)}")
    for status, name in waves:
        mark = "✅ Завершена" if status.lower() == "x" else "⏳ В ожидании"
        print(f"   [{mark}] {name.strip()}")

    print("✅ СТРУКТУРА ПЛАНИРОВАНИЯ ВАЛИДНА И ГОТОВА К ИСПОЛНЕНИЮ")
    return 0


if __name__ == "__main__":
    sys.exit(check_plan())
