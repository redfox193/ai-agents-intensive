#!/usr/bin/env python3
import re
import sys
from pathlib import Path

EARS_PATTERNS = [
    (r"^Система ДОЛЖНА\s+", "Ubiquitous (Вездесущий)"),
    (r"^КОГДА\s+.+,\s+система ДОЛЖНА\s+", "Event-driven (По событию)"),
    (r"^ПОКА\s+.+,\s+система ДОЛЖНА\s+", "State-driven (По состоянию)"),
    (r"^ЕСЛИ\s+.+,\s+система ДОЛЖНА\s+", "Optional (Опциональный)"),
    (r"^ЕСЛИ\s+.+,\s+ТО система ДОЛЖНА\s+", "Unwanted behavior (Нежелательное поведение)"),
]


def verify_ears_file(spec_path: Path):
    if not spec_path.exists():
        print(f"❌ Файл спецификации {spec_path} не найден!")
        return 1

    content = spec_path.read_text(encoding="utf-8")
    req_lines = [
        line.strip() for line in content.splitlines() if line.strip().startswith("- [REQ-")
    ]

    print(f"=== ЛИНТЕР СИНТАКСИСА ТРЕБОВАНИЙ EARS: {spec_path.name} ===")
    print(f"Обнаружено требований в спецификации: {len(req_lines)}")

    errors = 0
    classified = {name: 0 for _, name in EARS_PATTERNS}

    for line in req_lines:
        m = re.match(r"- \[([^\]]+)\]\s+(.+)", line)
        if not m:
            continue
        req_id, text = m.group(1), m.group(2)
        matched = False
        for pat, p_name in EARS_PATTERNS:
            if re.search(pat, text):
                classified[p_name] += 1
                matched = True
                break

        if not matched:
            print(f"❌ Нарушение EARS в {req_id}: '{text}'")
            print("   Требование не соответствует ни одному из 5 канонических шаблонов EARS!")
            errors += 1

    print("\nСводка распределения по паттернам EARS:")
    for p_name, count in classified.items():
        print(f"   [+] {p_name:<30}: {count} требований")

    if errors > 0:
        print(f"\n❌ ОБНАРУЖЕНО {errors} НАРУШЕНИЙ СИНТАКСИСА EARS")
        return 1

    print("\n✅ ВСЕ ТРЕБОВАНИЯ СТРОГО СООТВЕТСТВУЮТ СТАНДАРТУ EARS")
    return 0


if __name__ == "__main__":
    spec_file = Path("specs/billing-ears.md")
    sys.exit(verify_ears_file(spec_file))
