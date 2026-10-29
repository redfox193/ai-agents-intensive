#!/usr/bin/env python3
"""Легковесная проверка синхронизации базы знаний монолита.

- docs/INDEX.md существует и укладывается в лимит 100 строк.
- Все пути app/... и docs/domains/..., упомянутые в INDEX.md, существуют на диске.

Exit code: 0 — всё сходится, 1 — есть расхождения.
"""

import re
import sys
from pathlib import Path

MAX_LINES = 100

# Пути вида app/... и docs/domains/... (слоши, точки, дефисы, подчёркивания, расширения)
PATH_RE = re.compile(r"\b((?:app|docs/domains)/[\w./-]+)")

REASON_INDEX_MISSING = "INDEX_MISSING"
REASON_SIZE_EXCEEDED = "INDEX_SIZE_EXCEEDED"
REASON_FILE_MISSING = "FILE_MISSING"


def verify_kb(root: Path | None = None) -> int:
    """Проверить синхронизация базы знаний; вернуть 0 (OK) или 1 (FAIL)."""
    root = root or Path.cwd()
    index = root / "docs" / "INDEX.md"

    if not index.exists():
        print("FAIL: docs/INDEX.md не найден")
        return 1

    text = index.read_text(encoding="utf-8")
    lines = text.splitlines()
    errors: list[str] = []
    if len(lines) > MAX_LINES:
        errors.append(f"docs/INDEX.md содержит {len(lines)} строк (лимит {MAX_LINES})")

    missing: list[str] = []
    for rel in sorted(set(PATH_RE.findall(text))):
        p = root / rel
        # Упоминания путей в тексте могут стоять без расширения — допускаем файл с .md
        if not p.exists() and not Path(str(p) + ".md").exists():
            missing.append(rel)

    if errors or missing:
        print("FAIL: база знаний не синхронизирована с диском")
        for e in errors:
            print(f"  - {e}")
        for rel in missing:
            print(f"  - отсутствует: {rel}")
        return 1

    print(
        f"OK: docs/INDEX.md ({len(lines)}/{MAX_LINES} строк), "
        f"путей проверено: {len(set(PATH_RE.findall(text)))} — все существуют"
    )
    return 0


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    return verify_kb(root)


if __name__ == "__main__":
    sys.exit(main())
