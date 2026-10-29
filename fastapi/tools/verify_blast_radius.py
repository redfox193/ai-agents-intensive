#!/usr/bin/env python3
"""Blast Radius Guard: бюджет изменённых файлов и неприкосновенность замороженного ядра.

Источник правды — `git status --porcelain -uall`: каждый новый файл в неотслеживаемом каталоге
считается отдельно, переименование `R  старый -> новый` учитывает оба пути.
Контракт — `.agents/skills/blast-radius-guard/SKILL.md`: весь каталог `app/core/` и `alembic/`
защищён, новый файл в ядре допустим только из `allowed_new_core_files` спеки.
"""

import json
import subprocess
import sys
from pathlib import Path

PROTECTED_PREFIXES = ("app/core/", "alembic/")
DEFAULT_FROZEN_FILES = ("app/core/config.py", "app/core/security.py", "app/main.py")
DEFAULT_MAX_FILES = 7


def run_git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def clean_path(raw: str) -> str:
    return raw.strip().strip('"')


def get_git_changes() -> list[tuple[str, str, str | None]]:
    """Возвращает (статус XY, путь, прежний путь при переименовании) для файлов проекта.

    Проект может лежать в подкаталоге репозитория (например, `fastapi/`): git печатает пути от
    корня репозитория, а бюджет в specs/blast-radius.json задан от корня проекта.
    """
    status = run_git("status", "--porcelain", "-uall")
    prefix = run_git("rev-parse", "--show-prefix").strip()
    changes: list[tuple[str, str, str | None]] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        code = line[:2]
        paths = [clean_path(p) for p in line[3:].split(" -> ")]
        path, old = paths[-1], (paths[0] if len(paths) > 1 else None)
        if prefix and not (path.startswith(prefix) or (old or "").startswith(prefix)):
            continue
        changes.append((code, path[len(prefix) :], old[len(prefix) :] if old else None))
    return changes


def is_protected(path: str, frozen_files: set[str]) -> bool:
    return path in frozen_files or any(
        path == prefix.rstrip("/") or path.startswith(prefix) for prefix in PROTECTED_PREFIXES
    )


def is_new_file(code: str) -> bool:
    return code == "??" or code[0] == "A"


def verify_blast_radius() -> int:
    root = Path.cwd()
    spec_file = root / "specs" / "blast-radius.json"

    if not spec_file.exists():
        print("❌ specs/blast-radius.json не найден!")
        return 1

    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    max_files = spec.get("max_changed_files", DEFAULT_MAX_FILES)
    frozen_files = set(spec.get("frozen_paths", DEFAULT_FROZEN_FILES))
    allowed_new_core = set(spec.get("allowed_new_core_files", []))

    try:
        changes = get_git_changes()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"❌ Не удалось получить `git status --porcelain -uall`: {exc}")
        return 2
    changed_files = {path for _, path, _ in changes}

    print("=== ПРОВЕРКА БЮДЖЕТА ИЗМЕНЕНИЙ (BLAST RADIUS GUARD) ===")
    print(f"Всего затронуто файлов: {len(changed_files)} (лимит: <= {max_files})")

    # 1. Проверка лимита количества файлов
    if len(changed_files) > max_files:
        print(f"❌ BUDGET EXCEEDED: изменено {len(changed_files)} > {max_files}")
        print("   Список измененных файлов:")
        for cf in sorted(changed_files):
            print(f"   - {cf}")
        print("❌ ДЕКОМПОЗИРУЙТЕ ЗАДАЧУ НА БОЛЕЕ МЕЛКИЕ ВОЛНЫ!")
        return 1

    # 2. Проверка неприкосновенности ядра (app/core/, alembic/, frozen_paths)
    violations: list[str] = []
    for _code, path, old in changes:
        if old is not None and is_protected(old, frozen_files):
            violations.append(f"{old} (переименован в {path})")
        elif is_protected(path, frozen_files) and not (
            path in allowed_new_core and path not in frozen_files
        ):
            violations.append(path)

    if violations:
        print("❌ PROTECTED FILE MODIFIED: нарушена неприкосновенность замороженного ядра:")
        for violation in sorted(violations):
            print(f"   - Попытка модификации защищенного ядра: {violation}")
        print("❌ ИЗМЕНЕНИЕ ЯДРА ЗАПРЕЩЕНО БЕЗ СОГЛАСОВАНИЯ АРХИТЕКТОРА!")
        return 1

    print("✅ БЮДЖЕТ ИЗМЕНЕНИЙ СОБЛЮДЕН (BLAST RADIUS В НОРМЕ)")
    return 0


if __name__ == "__main__":
    sys.exit(verify_blast_radius())
