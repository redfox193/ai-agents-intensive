#!/usr/bin/env python3
"""Оркестратор проверок конвейера LINK-42: Coder → CODE_GATE → Reviewer → Gate-панель.

Скрипт не имитирует работу ролей. Он запускает настоящие команды, проверяет код возврата
каждой и останавливается на первой ошибке: `VERDICT: FAIL (<шаг>)` и код 1.
`VERDICT: READY` печатается только когда все шаги вернули 0. Журнал: handoff/pipeline-execution.log.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "handoff" / "pipeline-execution.log"
REQUIRED = (
    "AGENTS.md",
    "specs/LINK-42-enable-link.md",
    "docs/risk-plan-LINK-42.md",
    "docs/gate-rubric.md",
    "prompts/01-coder.md",
    "prompts/02-reviewer.md",
    "prompts/03-gate.md",
    ".ai-team/handoff-coder.md",
    ".ai-team/handoff-reviewer.md",
    ".ai-team/verdict.md",
)


def log(message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run(name: str, argv: list[str], env: dict[str, str] | None = None) -> bool:
    result = subprocess.run(
        argv,
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )
    log(f"{name}: код возврата {result.returncode}")
    if result.returncode != 0:
        tail = (result.stdout + result.stderr).strip()[-1500:]
        log(f"{name}: вывод (хвост):\n{tail}")
    return result.returncode == 0


def first_line(relative: str) -> str:
    text = (ROOT / relative).read_text(encoding="utf-8").strip()
    return text.splitlines()[0].strip() if text else ""


def check_artifacts() -> bool:
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        log(f"артефакты отсутствуют: {missing}")
        return False
    coder = (ROOT / ".ai-team/handoff-coder.md").read_text(encoding="utf-8")
    if "<" in coder and ">" in coder.split("<", maxsplit=1)[1]:
        log("handoff-coder.md содержит незаполненные плейсхолдеры <...>")
        return False
    if first_line(".ai-team/handoff-reviewer.md") != "Вердикт: ACCEPT":
        log("handoff-reviewer.md: первая строка не «Вердикт: ACCEPT»")
        return False
    if first_line(".ai-team/verdict.md") != "Вердикт: READY":
        log(".ai-team/verdict.md: первая строка не «Вердикт: READY»")
        return False
    log("артефакты .ai-team/: handoff-coder, ACCEPT ревьюера и READY гейта на месте")
    return True


def main() -> int:
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text("=== ЖУРНАЛ ИСПОЛНЕНИЯ КОНВЕЙЕРА LINK-42 ===\n", encoding="utf-8")
    py = sys.executable
    with tempfile.TemporaryDirectory(prefix="linksvc-alembic-") as tmp:
        db = {"DATABASE_URL": f"sqlite+aiosqlite:///{Path(tmp) / 'migrate.db'}"}
        steps: list[tuple[str, list[str], dict[str, str] | None]] = [
            ("ruff check", [py, "-m", "ruff", "check", "."], None),
            ("ruff format --check", [py, "-m", "ruff", "format", "--check", "."], None),
            ("basedpyright", [py, "-m", "basedpyright"], None),
            ("pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], None),
            ("alembic upgrade head", [py, "-m", "alembic", "upgrade", "head"], db),
            ("alembic check", [py, "-m", "alembic", "check"], db),
            ("mutate_probe", [py, "scripts/mutate_probe.py"], None),
        ]
        log("ЭТАП 1: наличие артефактов и пакетов ролей")
        if not check_artifacts():
            print("VERDICT: FAIL (artifacts)")
            return 1
        log("ЭТАП 2: CODE_GATE и мутационная проверка (настоящие команды)")
        for name, argv, env in steps:
            if not run(name, argv, env):
                print(f"VERDICT: FAIL ({name})")
                return 1
        log("ЭТАП 3: Gate-панель — голоса и протокол")
        if not run("generate_proof", [py, "scripts/generate_proof.py"]):
            print("VERDICT: FAIL (generate_proof)")
            return 1
    log("КОНВЕЙЕР ПРОЙДЕН: все шаги вернули 0")
    print("VERDICT: READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
