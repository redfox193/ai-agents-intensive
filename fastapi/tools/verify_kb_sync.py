#!/usr/bin/env python3
import re
import sys
from pathlib import Path


def verify_kb():
    root = Path.cwd()
    index_file = root / "docs" / "INDEX.md"

    if not index_file.exists():
        print("❌ ОШИБКА: docs/INDEX.md не найден!")
        return 1

    index_content = index_file.read_text(encoding="utf-8")
    lines = index_content.splitlines()

    if len(lines) > 100:
        print(
            f"❌ ОШИБКА: docs/INDEX.md превышает лимит размера! Строк: {len(lines)} (максимум 100)"
        )
        return 1

    # Извлекаем все пути к файлам вида `app/...`
    referenced_files = re.findall(r"`(app/[^`]+)`", index_content)
    missing_files = []

    for rel_path in referenced_files:
        full_path = root / rel_path
        if not full_path.exists():
            missing_files.append(rel_path)

    # Проверяем существование доменных спек
    referenced_specs = re.findall(r"`(docs/domains/[^`]+)`", index_content)
    missing_specs = []
    for spec in referenced_specs:
        if not (root / spec).exists():
            missing_specs.append(spec)

    print("=== ПРОВЕРКА АКТУАЛЬНОСТИ БАЗЫ ЗНАНИЙ (KNOWLEDGE SYNC) ===")
    print(f"Размер docs/INDEX.md: {len(lines)} строк (норма: <= 100) -> OK")
    print(f"Упомянуто файлов реализации: {len(referenced_files)}")
    print(f"Упомянуто доменных спецификаций: {len(referenced_specs)}")

    has_errors = False
    if missing_files:
        print("❌ BreakageSignal FILE_RENAMED / FILE_MISSING:")
        for mf in missing_files:
            print(f"   - Файл из индекса не найден на диске: {mf}")
        has_errors = True

    if missing_specs:
        print("❌ BreakageSignal SPEC_MISSING:")
        for ms in missing_specs:
            print(f"   - Документ домена не найден: {ms}")
        has_errors = True

    if has_errors:
        print("❌ ВЕРИФИКАЦИЯ БАЗЫ ЗНАНИЙ ПРОВАЛЕНА")
        return 1

    print("✅ БАЗА ЗНАНИЙ ПОЛНОСТЬЮ СИНХРОНИЗИРОВАНА С КОДОМ")
    return 0


if __name__ == "__main__":
    sys.exit(verify_kb())
