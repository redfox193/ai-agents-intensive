#!/usr/bin/env python3
"""Нейтральный оркестратор цикла разработки: Кодер → CODE_GATE → Панель техлидов → Суммаризатор.

Режимы:
* без аргументов / `--check` — быстрая проверка артефактов и пакета (< 2 с).
  Выводит последней строкой:
    `VERDICT: READY` (код 0)
    `VERDICT: REWORK` (код 1)
    `VERDICT: GATE_FAILURE (<причина>)` (код 1)
    `VERDICT: ESCALATE` (код 2)
* `--run-gates` — запуск детерминированного CODE_GATE проекта перед проверкой
  с фиксацией в `.ai-team/code-gate.json`.
* `--live` — запуск реальных агентов через `opencode run` с изолированными процессами.
  `--dry-run` вместе с `--live` выводит команды без их исполнения.

Модели судей панели (OpenCode Go / Multi-Model Matrix):
* Judge 1 (Скептик): `opencode-go/deepseek-v4.1-flash`
* Judge 2 (Реалист): `opencode-go/glm-5.3-flash`
* Judge 3 (Визионер): `opencode-go/qwen3.8-flash`
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Канонические модели по умолчанию (OpenCode Go)
DEFAULT_JUDGE1_MODEL = "opencode-go/deepseek-v4.1-flash"
DEFAULT_JUDGE2_MODEL = "opencode-go/glm-5.3-flash"
DEFAULT_JUDGE3_MODEL = "opencode-go/qwen3.8-flash"
DEFAULT_CODER_MODEL = "opencode-go/deepseek-v4.1-flash"
DEFAULT_SUMMARIZER_MODEL = "opencode-go/glm-5.3-flash"

DEFAULT_TASK_ID = "BILLING-01"
DEFAULT_SPEC = "specs/billing-ears.md"
DEFAULT_MAX_CYCLES = 3

EXIT_READY = 0
EXIT_REWORK = 1
EXIT_GATE_FAILURE = 1
EXIT_ESCALATE = 2


def find_root() -> Path:
    """Динамическое определение корня проекта без привязки к конкретной машине."""
    current = Path(__file__).resolve().parent.parent
    if (current / "pyproject.toml").is_file():
        return current
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        top_path = Path(top)
        if (top_path / "fastapi" / "pyproject.toml").is_file():
            return top_path / "fastapi"
        return top_path
    except Exception:
        return current


ROOT = find_root()


@dataclass(frozen=True)
class JudgeConfig:
    judge1_model: str = DEFAULT_JUDGE1_MODEL
    judge2_model: str = DEFAULT_JUDGE2_MODEL
    judge3_model: str = DEFAULT_JUDGE3_MODEL
    coder_model: str = DEFAULT_CODER_MODEL
    summarizer_model: str = DEFAULT_SUMMARIZER_MODEL


@dataclass
class Finding:
    id: str
    severity: str  # BLOCKER, IMPORTANT, MINOR
    location: str  # file:line
    summary: str
    judge: str


def resolve_models(
    args: argparse.Namespace | None = None,
    env: Mapping[str, str] | None = None,
    config_path: Path | None = None,
) -> JudgeConfig:
    """Разрешение моделей с приоритетами: CLI флаги -> Переменные окружения -> Конфиг -> Дефолты."""
    environ = os.environ if env is None else env
    cfg_file = config_path or (ROOT / "opencode.json")

    # Чтение модели из opencode.json если есть
    cfg_default_model: str | None = None
    if cfg_file.is_file():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            cfg_default_model = cfg.get("model")
        except Exception:
            pass

    global_override = (
        getattr(args, "model", None) or environ.get("OPENCODE_MODEL") or cfg_default_model
    )

    j1 = (
        getattr(args, "model_judge1", None)
        or environ.get("OPENCODE_MODEL_JUDGE1")
        or global_override
        or DEFAULT_JUDGE1_MODEL
    )
    j2 = (
        getattr(args, "model_judge2", None)
        or environ.get("OPENCODE_MODEL_JUDGE2")
        or global_override
        or DEFAULT_JUDGE2_MODEL
    )
    j3 = (
        getattr(args, "model_judge3", None)
        or environ.get("OPENCODE_MODEL_JUDGE3")
        or global_override
        or DEFAULT_JUDGE3_MODEL
    )
    coder = (
        getattr(args, "model_coder", None)
        or environ.get("OPENCODE_MODEL_CODER")
        or global_override
        or DEFAULT_CODER_MODEL
    )
    summarizer = (
        getattr(args, "model_summarizer", None)
        or environ.get("OPENCODE_MODEL_SUMMARIZER")
        or global_override
        or DEFAULT_SUMMARIZER_MODEL
    )

    return JudgeConfig(
        judge1_model=j1,
        judge2_model=j2,
        judge3_model=j3,
        coder_model=coder,
        summarizer_model=summarizer,
    )


def build_opencode_command(model: str, prompt: str) -> list[str]:
    """Формирование команды запуска OpenCode в изолированном процессе."""
    return ["opencode", "run", "-m", model, "--format", "json", prompt]


def run_code_gate(root: Path) -> tuple[bool, str, dict[str, Any]]:
    """Выполнение детерминированных проверок CODE_GATE."""
    commands: list[tuple[str, str]] = []

    # Проверка наличия комплексного скрипта проверки техлида
    techlead_gate_tool = root / "tools" / "verify_techlead_gate.py"
    if techlead_gate_tool.is_file():
        commands.append(("verify_techlead_gate", f"python3 {techlead_gate_tool}"))
    else:
        # Стандартные ступени
        kb_tool = root / "tools" / "verify_kb_sync.py"
        if kb_tool.is_file():
            commands.append(("kb_sync", f"python3 {kb_tool}"))
        commands.append(("pytest", "uv run pytest -q"))
        blast_tool = root / "tools" / "verify_blast_radius.py"
        if blast_tool.is_file():
            commands.append(("blast_radius", f"python3 {blast_tool}"))
        layers_tool = root / "tools" / "verify_architecture_layers.py"
        if layers_tool.is_file():
            commands.append(("layers", f"python3 {layers_tool}"))

    gate_results: list[dict[str, Any]] = []
    all_passed = True
    failed_reason = ""

    for name, cmd in commands:
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=300,
            )
            success = res.returncode == 0
            gate_results.append(
                {
                    "step": name,
                    "command": cmd,
                    "exit_code": res.returncode,
                    "stdout_tail": res.stdout[-500:],
                    "stderr_tail": res.stderr[-500:],
                }
            )
            if not success and all_passed:
                all_passed = False
                failed_reason = f"{name} (rc={res.returncode})"
        except Exception as exc:
            all_passed = False
            failed_reason = f"{name} (exception: {exc})"
            gate_results.append(
                {
                    "step": name,
                    "command": cmd,
                    "exit_code": -1,
                    "error": str(exc),
                }
            )
            break

    payload = {
        "status": "PASS" if all_passed else "FAIL",
        "steps": gate_results,
    }

    # Запись свидетельства
    code_gate_path = root / ".ai-team" / "code-gate.json"
    code_gate_path.parent.mkdir(parents=True, exist_ok=True)
    code_gate_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if not all_passed:
        # Создание gate-failure brief для Кодера
        failure_brief = {
            "title": "CODE_GATE Failure Brief",
            "reason": failed_reason,
            "failed_steps": [r for r in gate_results if r.get("exit_code") != 0],
            "action_required": "Исправить упавшие проверки до повторного запуска коллегии",
        }
        brief_path = root / "handoff" / "gate-failure-brief.json"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        brief_path.write_text(
            json.dumps(failure_brief, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return all_passed, failed_reason, payload


def build_judge_prompt(
    seat: str, hat: str, spec_path: Path, changed_files: Sequence[str], root: Path
) -> str:
    """Формирование декларативного брифа для судьи в соответствующей шляпе."""
    return (
        f"Роль: {seat} в шляпе [{hat}]. "
        f"Спецификация: {spec_path.relative_to(root) if spec_path.is_relative_to(root) else spec_path}. "
        f"Изменённые файлы: {', '.join(changed_files) if changed_files else 'согласно git status'}. "
        f"Задача: провести независимый аудит изменений. "
        f"Шляпа Скептика проверяет риски, дыры и утечки. "
        f"Шляпа Реалиста проверяет соответствие спеке, исполняемость и тесты. "
        f"Шляпа Визионера проверяет границы слоёв и архитектурную чистоту. "
        f'Формат ответа JSON: {{"verdict": "ACCEPT" | "REJECT", '
        f'"findings": [{{"id": "F-001", "severity": "BLOCKER"|"IMPORTANT"|"MINOR", '
        f'"location": "файл:строка", "summary": "описание дефекта"}}]}}'
    )


def summarize_rework(findings: list[Finding], root: Path) -> dict[str, Any]:
    """Суммаризатор: объединение находок судей в структурированный panel-rework-brief.json."""
    instructions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for idx, f in enumerate(findings, start=1):
        dedup_key = f"{f.location}:{f.summary.strip().lower()}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        rw_id = f"RW-{idx:03d}"
        instructions.append(
            {
                "id": rw_id,
                "severity": f.severity,
                "location": f.location,
                "issue": f.summary,
                "judge_source": f.judge,
                "action": f"Устранить дефект по адресу {f.location}: {f.summary}",
            }
        )

    brief_data = {
        "title": "Panel Rework Brief",
        "schema_version": "1.0",
        "total_instructions": len(instructions),
        "blocking_count": sum(1 for i in instructions if i["severity"] in ("BLOCKER", "IMPORTANT")),
        "instructions": instructions,
    }

    out_path = root / "handoff" / "panel-rework-brief.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(brief_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return brief_data


def evaluate_package(root: Path, max_cycles: int = DEFAULT_MAX_CYCLES) -> tuple[int, str]:
    """Оценка состояния пакета и вынесение итогового вердикта."""
    panel_dir = root / ".ai-team" / "panel"
    code_gate_file = root / ".ai-team" / "code-gate.json"
    rework_brief_file = root / "handoff" / "panel-rework-brief.json"
    gate_failure_brief = root / "handoff" / "gate-failure-brief.json"

    # 1. Проверка CODE_GATE
    if code_gate_file.is_file():
        try:
            gate_data = json.loads(code_gate_file.read_text(encoding="utf-8"))
            if gate_data.get("status") == "FAIL":
                failed_step = "unknown"
                for step in gate_data.get("steps", []):
                    if step.get("exit_code") != 0:
                        failed_step = step.get("step", "gate")
                        break
                return EXIT_GATE_FAILURE, f"VERDICT: GATE_FAILURE ({failed_step})"
        except Exception:
            return EXIT_GATE_FAILURE, "VERDICT: GATE_FAILURE (corrupted code-gate.json)"
    elif gate_failure_brief.is_file():
        return EXIT_GATE_FAILURE, "VERDICT: GATE_FAILURE (gate failure brief present)"

    # 2. Проверка наличия судейских оценок
    judge_files = sorted(panel_dir.glob("judge-*.json")) if panel_dir.is_dir() else []

    # Если файлов судей нет, но есть rework brief -> REWORK
    if not judge_files and rework_brief_file.is_file():
        return EXIT_REWORK, "VERDICT: REWORK"

    if not judge_files:
        # Проверяем, есть ли готовый вердикт маркдаун
        verdict_md = root / ".ai-team" / "verdict.md"
        if verdict_md.is_file():
            text = verdict_md.read_text(encoding="utf-8")
            if "Вердикт: READY" in text or "VERDICT: READY" in text:
                return EXIT_READY, "VERDICT: READY"
            if "Вердикт: REWORK" in text or "VERDICT: REWORK" in text:
                return EXIT_REWORK, "VERDICT: REWORK"
            if "Вердикт: ESCALATE" in text or "VERDICT: ESCALATE" in text:
                return EXIT_ESCALATE, "VERDICT: ESCALATE"
        return EXIT_ESCALATE, "VERDICT: ESCALATE (no judge evaluations or verdict found)"

    all_findings: list[Finding] = []
    any_reject = False

    for jf in judge_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            verdict = data.get("verdict", "").upper()
            if verdict == "REJECT":
                any_reject = True
            for raw_f in data.get("findings", []):
                all_findings.append(
                    Finding(
                        id=raw_f.get("id", "F-000"),
                        severity=raw_f.get("severity", "MINOR").upper(),
                        location=raw_f.get("location", "unknown:0"),
                        summary=raw_f.get("summary", ""),
                        judge=jf.stem,
                    )
                )
        except Exception:
            return EXIT_ESCALATE, f"VERDICT: ESCALATE (invalid judge file: {jf.name})"

    blocking = [f for f in all_findings if f.severity in ("BLOCKER", "IMPORTANT")]

    if any_reject or blocking:
        summarize_rework(all_findings, root)
        return EXIT_REWORK, "VERDICT: REWORK"

    return EXIT_READY, "VERDICT: READY"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Нейтральный оркестратор Coder → CODE_GATE → Панель техлидов (OpenCode Free Tier) → Summarizer."
    )
    parser.add_argument(
        "--run-gates", action="store_true", help="Запустить CODE_GATE проекта перед оценкой."
    )
    parser.add_argument(
        "--live", action="store_true", help="Выполнить реальный запуск агентов через opencode."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Вместе с --live только вывести команды."
    )
    parser.add_argument(
        "--task-id", default=DEFAULT_TASK_ID, help="Идентификатор задачи (по умолчанию BILLING-01)."
    )
    parser.add_argument(
        "--spec", default=DEFAULT_SPEC, help="Путь к спеке (по умолчанию specs/billing-ears.md)."
    )
    parser.add_argument(
        "--max-cycles", type=int, default=DEFAULT_MAX_CYCLES, help="Максимальное число циклов."
    )
    parser.add_argument("--model", help="Единый override модели OpenCode для всех ролей.")
    parser.add_argument(
        "--model-judge1", help=f"Модель Judge-1 (Скептик), дефолт: {DEFAULT_JUDGE1_MODEL}."
    )
    parser.add_argument(
        "--model-judge2", help=f"Модель Judge-2 (Реалист), дефолт: {DEFAULT_JUDGE2_MODEL}."
    )
    parser.add_argument(
        "--model-judge3", help=f"Модель Judge-3 (Визионер), дефолт: {DEFAULT_JUDGE3_MODEL}."
    )
    parser.add_argument("--model-coder", help=f"Модель Кодера, дефолт: {DEFAULT_CODER_MODEL}.")
    parser.add_argument(
        "--model-summarizer", help=f"Модель Суммаризатора, дефолт: {DEFAULT_SUMMARIZER_MODEL}."
    )

    args = parser.parse_args(argv)
    cfg = resolve_models(args)
    root = ROOT

    print(f"=== Оркестратор приёмки (Задача: {args.task_id}) ===")
    print(f"Корень проекта: {root}")
    print(
        f"Панель судей OpenCode: [1] {cfg.judge1_model} (Скептик), "
        f"[2] {cfg.judge2_model} (Реалист), [3] {cfg.judge3_model} (Визионер)"
    )

    if args.run_gates:
        print("\n--- Запуск детерминированного CODE_GATE ---")
        passed, reason, _ = run_code_gate(root)
        if not passed:
            print(f"❌ CODE_GATE завершился ошибкой: {reason}")
            print(f"VERDICT: GATE_FAILURE ({reason})")
            return EXIT_GATE_FAILURE
        print("✅ CODE_GATE успешно пройден")

    if args.live:
        print("\n--- Режим LIVE (OpenCode subprocesses) ---")
        commands: list[list[str]] = [
            build_opencode_command(cfg.judge1_model, "Аудит в шляпе Скептика"),
            build_opencode_command(cfg.judge2_model, "Аудит в шляпе Реалиста"),
            build_opencode_command(cfg.judge3_model, "Аудит в шляпе Визионера"),
        ]
        for cmd in commands:
            cmd_str = " ".join(cmd)
            if args.dry_run:
                print(f"[DRY-RUN] {cmd_str}")
            else:
                print(f"Запуск: {cmd[0]} {cmd[1]} -m {cmd[3]} ...")
                # В реальном live-режиме запускаем свежий процесс без stdin
                subprocess.run(cmd, stdin=subprocess.DEVNULL, cwd=str(root))

    code, verdict_str = evaluate_package(root, max_cycles=args.max_cycles)
    print(verdict_str)
    return code


if __name__ == "__main__":
    sys.exit(main())
