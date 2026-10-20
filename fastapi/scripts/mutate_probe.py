#!/usr/bin/env python3
"""Мутационная проверка чувствительности тестов LINK-42 на настоящих `app/` и `tests/`.

Каждая мутация правит один фрагмент исходника приложения, запускает настоящий `pytest -q`
и требует, чтобы тесты упали (мутант убит). Исходный файл гарантированно восстанавливается.

Коды выхода: 0 — все мутанты убиты; 1 — исходные тесты красные или мутант выжил;
2 — нет `app/` или `tests/flat_api/test_links.py`, либо фрагмент для мутации не найден.
"""

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

ROOT = Path(__file__).resolve().parent.parent
TESTS_FILE = ROOT / "tests" / "flat_api" / "test_links.py"
REPOSITORY = ROOT / "app" / "repositories" / "link.py"
SERVICE = ROOT / "app" / "services" / "link.py"
SCHEMAS = ROOT / "app" / "schemas" / "link.py"
APP_FILES = (REPOSITORY, SERVICE)
PYTEST_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class Mutant:
    name: str
    path: Path
    old: str
    new: str


MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        "set_active: инверсия флага",
        REPOSITORY,
        "link.is_active = is_active",
        "link.is_active = not is_active",
    ),
    Mutant(
        "increment_clicks: шаг +2 вместо +1",
        REPOSITORY,
        "values(clicks=Link.clicks + 1)",
        "values(clicks=Link.clicks + 2)",
    ),
    Mutant(
        "increment_clicks: счётчик не растёт",
        REPOSITORY,
        "values(clicks=Link.clicks + 1)",
        "values(clicks=Link.clicks)",
    ),
    Mutant(
        "resolve_link: отключённая ссылка пропускается",
        SERVICE,
        "if not link.is_active:\n            raise LinkInactiveError",
        "if link.is_active:\n            raise LinkInactiveError",
    ),
    Mutant(
        "resolve_link: несуществующая ссылка не даёт ошибку",
        SERVICE,
        "if link is None:\n            raise LinkNotFoundError(f\"Ссылка с кодом '{short_code}' не найдена\")\n"
        "        if not link.is_active",
        "if link is not None:\n            raise LinkNotFoundError(f\"Ссылка с кодом '{short_code}' не найдена\")\n"
        "        if not link.is_active",
    ),
    Mutant(
        "ttl_seconds: допускается нулевой TTL",
        SCHEMAS,
        "gt=0,\n        le=31536000",
        "ge=0,\n        le=31536000",
    ),
    Mutant(
        "redirect: статус 302 вместо 307",
        ROOT / "app" / "main.py",
        "status_code=307",
        "status_code=302",
    ),
)


def run_pytest() -> int:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=PYTEST_TIMEOUT_SECONDS,
        check=False,
    )
    return result.returncode


def on_terminate(_signum: int, _frame: FrameType | None) -> None:
    raise SystemExit(130)


def check_prerequisites() -> list[str]:
    problems: list[str] = []
    if not any(path.is_file() for path in APP_FILES):
        problems.append("нет ни app/repositories/link.py, ни app/services/link.py")
    if not TESTS_FILE.is_file():
        problems.append("нет tests/flat_api/test_links.py")
    for mutant in MUTANTS:
        if not mutant.path.is_file():
            problems.append(f"нет файла для мутации: {mutant.path.relative_to(ROOT)}")
        elif mutant.old not in mutant.path.read_text(encoding="utf-8"):
            problems.append(f"фрагмент не найден: {mutant.path.relative_to(ROOT)}: {mutant.old!r}")
    return problems


def apply_mutant(mutant: Mutant) -> int:
    original = mutant.path.read_bytes()
    stat = mutant.path.stat()
    try:
        mutant.path.write_text(
            original.decode("utf-8").replace(mutant.old, mutant.new, 1), encoding="utf-8"
        )
        return run_pytest()
    finally:
        mutant.path.write_bytes(original)
        os.utime(mutant.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))


def main() -> int:
    signal.signal(signal.SIGTERM, on_terminate)
    print("[МУТАЦИОННЫЙ АУДИТ] Мутации настоящих app/ и прогон настоящих tests/ ...")
    problems = check_prerequisites()
    if problems:
        for problem in problems:
            print(f"ОШИБКА: {problem}", file=sys.stderr)
        return 2

    if run_pytest() != 0:
        print("ОШИБКА: исходные тесты красные, мутационный аудит невозможен.", file=sys.stderr)
        return 1
    print("✓ Исходный код проходит настоящий pytest.")

    killed = 0
    survivors: list[str] = []
    for mutant in MUTANTS:
        code = apply_mutant(mutant)
        if code == 1:
            print(f"✓ Мутант [{mutant.name}] УБИТ: pytest упал.")
            killed += 1
        elif code == 0:
            print(f"✗ Мутант [{mutant.name}] ВЫЖИЛ: pytest остался зелёным.")
            survivors.append(mutant.name)
        else:
            print(f"ОШИБКА: pytest завершился кодом {code} на мутанте [{mutant.name}].")
            return 2

    total = len(MUTANTS)
    print(f"\n[ИТОГ] Mutation Score: {killed / total * 100:.1f}% ({killed}/{total} убито)")
    if survivors:
        print("ОТКЛОНЕНО: тесты пропустили мутантов: " + "; ".join(survivors), file=sys.stderr)
        return 1
    print("✓ ПРИНЯТО: все мутанты убиты настоящими тестами.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
