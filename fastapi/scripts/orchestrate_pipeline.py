#!/usr/bin/env python3
"""Оркестратор внешнего цикла приёмки LINK-42: Кодер → CODE_GATE → Панель техлидов.

Скрипт не имитирует работу ролей и не придумывает оценок за судей.

Режимы:

* без аргументов — быстрая детерминированная проверка готового пакета (меньше 2 с):
  артефакты, handoff Кодера, свидетельство CODE_GATE, панель консенсуса. Последняя строка
  вывода: `VERDICT: READY` (код 0), `VERDICT: FAIL (<шаг>)` или `VERDICT: REJECT` (код 1),
  `VERDICT: ESCALATE` (код 2);
* `--run-gates` — перед проверкой выполнить настоящие команды CODE_GATE и записать
  `.ai-team/code-gate.json` (`source: live`), если свидетельство изменилось по существу;
* `--live` — настоящий внешний цикл до 5 циклов через `opencode run`: отдельный свежий
  процесс на каждого Кодера, судью, раунд и суммаризацию, stdin закрыт, без продолжения
  чужих сессий. `--dry-run` вместе с `--live` только печатает последовательность команд.

Журнал: `handoff/pipeline-execution.log`. Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_handoff  # noqa: E402  # путь скриптов добавлен строкой выше

ROOT = Path(__file__).resolve().parent.parent
LOG_RELATIVE = "handoff/pipeline-execution.log"

TASK_ID = "LINK-42"
DEFAULT_MODEL = "opencode/deepseek-v4.1-flash-free"
MODEL_ENV = "OPENCODE_MODEL"
MAX_CYCLES = 5
OPENCODE_TIMEOUT_S = 3600
GATE_TIMEOUT_S = 1800
TAIL_CHARS = 1500
JUDGE_ATTEMPTS = 2

SPEC = "specs/LINK-42-enable-link.md"
RISK_PLAN = "docs/risk-plan-LINK-42.md"
RUBRIC = "docs/gate-rubric.md"
HANDOFF_MD = ".ai-team/handoff-coder.md"
CODE_GATE_JSON = ".ai-team/code-gate.json"
PANEL_DIR = ".ai-team/panel"
MANIFEST_JSON = f"{PANEL_DIR}/manifest.json"
LEDGER_TSV = f"{PANEL_DIR}/findings-ledger.tsv"
FREEZE_JSON = f"{PANEL_DIR}/freeze.json"
REWORK_BRIEF = "handoff/panel-rework-brief.json"
GATE_FAILURE_BRIEF = "handoff/gate-failure-brief.json"
PANEL_SKILL = ".agents/skills/teamlead-panel/SKILL.md"
CONSENSUS_DOC = ".agents/skills/teamlead-panel/references/consensus-debate.md"
REWORK_BRIEF_SCHEMA = ".agents/skills/teamlead-panel/references/panel-rework-brief-schema.md"
FEATURE_SKILL = ".agents/skills/feature/SKILL.md"
REWORK_SKILL = ".agents/skills/rework/SKILL.md"
OPENCODE_CONFIG = "opencode.json"
BASE_REF = "main"
PRODUCT_PATHS = ("app", "tests", "alembic")
DIFF_COMMAND = f"git diff {BASE_REF}...HEAD -- {' '.join(PRODUCT_PATHS)}"
# Эталонные sha256 защищённых файлов; `None` — файл Дня 1, которого в ветке нет и не должно быть.
PROTECTED_FILE_SHA256: Mapping[str, str | None] = {
    "AGENTS.md": "32f01dcf939b38cfc07340d289dcf15ad2bec4f52b446e2c6157020978824bbc",
    ".agents/AGENTS.md": "9a2414d45208f79a769eebb3bbd1922721d5996612781bd010c7532a9a3401ce",
    "pyproject.toml": "252464c12a8b9f60d7874606008ab60db36f955d9b4316f39dc2919049d31dc1",
    "uv.lock": "b0ff8cd44a7165a4764a47f574fd1f77b2a215c4db4fa2f697c699d235ff260a",
    SPEC: "0d45b19a5d38ae19550b50222a828b0ffbc303cf34bbc92f022737bc30a8f004",
    **dict.fromkeys(
        (
            f".agents/skills/{name}/SKILL.md"
            for name in ("onboard", "specify", "test-first", "entrypoint", "self-check")
        ),
    ),
}
PROTECTED_FILES = tuple(PROTECTED_FILE_SHA256)
FINGERPRINT_SKIP_TOP = frozenset({".ai-team", "handoff"})
FINGERPRINT_SKIP_ANY = frozenset(
    {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
)
ALLOWED_HEADING = "Разрешённые файлы для изменения"
FORBIDDEN_HEADING = "СТРОГО ЗАПРЕЩЕНО"
PATH_TOKEN = re.compile(r"`([A-Za-z0-9_./-]+)`")
BLAST_STEP_LABEL = "uv run python scripts/orchestrate_pipeline.py --check-blast-radius"
GIT_TIMEOUT_S = 60

REQUIRED = (
    "AGENTS.md",
    SPEC,
    RISK_PLAN,
    RUBRIC,
    "prompts/01-coder.md",
    "prompts/03-gate.md",
    HANDOFF_MD,
    CODE_GATE_JSON,
    MANIFEST_JSON,
)
GATE_REQUIRED = (
    "ruff check",
    "basedpyright",
    "alembic check",
    "pytest",
    "mutate_probe",
    "check-blast-radius",
)
SEATS = ("judge-1", "judge-2", "judge-3")
DEBATE_ROUNDS = ("R1", "D1", "D2", "D3")
FINAL_ROUND = "C1"
HATS: Mapping[str, tuple[str, str, str]] = {
    "R1": ("Скептик", "Реалист", "Визионер"),
    "D1": ("Реалист", "Визионер", "Скептик"),
    "D2": ("Визионер", "Скептик", "Реалист"),
    "D3": ("Скептик", "Реалист", "Визионер"),
    "C1": ("Общая", "Общая", "Общая"),
}
HAT_FOCUS: Mapping[str, str] = {
    "Скептик": "риски, дыры в контрактах, утечки секретов (CWE-532), граничные случаи",
    "Реалист": "простота, исполнимость, тесты, сопровождение, соответствие спеке и риск-плану",
    "Визионер": "границы слоёв, лишние зависимости, костыли, технический долг",
    "Общая": "итоговое решение по замороженному пакету, без чужих ответов",
}
VERDICT_EXIT: Mapping[str, int] = {"READY": 0, "REJECT": 1, "ESCALATE": 2}

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
HEX64 = re.compile(r"[0-9a-f]{64}")
VERDICT_LINE = re.compile(r"^VERDICT: (READY|REJECT|ESCALATE)$")
HEADER_START = re.compile(r"^SEAT:", re.MULTILINE)
LEDGER_COLUMNS = 7
LEDGER_STATUS_COLUMN = 5
LEDGER_MARKER = "### " + LEDGER_TSV + "\n"
DIFF_LIMIT = 150_000
FATAL_EVENT_TYPES = frozenset({"error", "session_error", "session.error", "fatal"})


class JudgeReadOnlyViolationError(RuntimeError):
    """Судья изменил файл вне `.ai-team/` и `handoff/` в режиме STRICT READ-ONLY."""


# --------------------------------------------------------------------------------------
# Журнал и запуск процессов
# --------------------------------------------------------------------------------------


class Journal:
    """Потокобезопасный журнал: печатает строку и дописывает её в файл."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def reset(self, title: str) -> None:
        """Создать журнал заново с заголовком."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(f"=== {title} ===\n", encoding="utf-8")

    def write(self, message: str) -> None:
        """Напечатать строку журнала с отметкой времени и дописать её в файл."""
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        with self._lock:
            print(line, flush=True)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


@dataclass(frozen=True)
class RunResult:
    """Результат запуска внешнего процесса."""

    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str]], RunResult]


def make_runner(
    cwd: Path, env: Mapping[str, str] | None = None, timeout: float | None = None
) -> Runner:
    """Собрать запускатель процессов: список аргументов, stdin закрыт, без shell."""

    def runner(argv: Sequence[str]) -> RunResult:
        try:
            done = subprocess.run(
                list(argv),
                cwd=cwd,
                env={**os.environ, **(env or {})},
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return RunResult(124, "", f"таймаут клиента {timeout} с")
        except OSError as error:
            return RunResult(127, "", f"не удалось запустить {argv[0]}: {error}")
        return RunResult(done.returncode, done.stdout, done.stderr)

    return runner


def tail(text: str, limit: int = TAIL_CHARS) -> str:
    """Хвост текста для журнала."""
    return text.strip()[-limit:]


def sha256_of(path: Path) -> str:
    """sha256 содержимого файла."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------------------
# Модель, команды opencode, брифы (чистые функции)
# --------------------------------------------------------------------------------------


def configured_models(config: Path) -> dict[str, str]:
    """Поля `model` и `small_model` из opencode.json; нет файла или поля — `ValueError`."""
    try:
        data: object = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{config.name}: не читается ({error})") from error
    mapping = cast(dict[str, object], data) if isinstance(data, dict) else {}
    found: dict[str, str] = {}
    for key in ("model", "small_model"):
        value = mapping.get(key)
        if not isinstance(value, str):
            raise ValueError(f"{config.name}: нет строки {key}")
        found[key] = value
    return found


def resolve_model(
    cli_model: str | None, environ: Mapping[str, str], config: Path = ROOT / OPENCODE_CONFIG
) -> str:
    """Выбрать модель: `--model`, `OPENCODE_MODEL`, затем `model` из opencode.json.

    Допустима только каноническая `DEFAULT_MODEL`: и запрошенная, и сконфигурированная
    (`model`, `small_model`) модель обязаны ей равняться, иначе — `ValueError`.
    """
    configured = configured_models(config)
    for key, value in configured.items():
        if value != DEFAULT_MODEL:
            raise ValueError(f"{config.name}: {key}={value!r}, допустима только {DEFAULT_MODEL}")
    requested = cli_model or environ.get(MODEL_ENV) or configured["model"]
    if requested != DEFAULT_MODEL:
        raise ValueError(f"модель {requested!r} не допускается: только {DEFAULT_MODEL}")
    return requested


def build_opencode_command(model: str, brief: str) -> list[str]:
    """Команда одного свежего процесса: без `--continue` и `--session`, вывод JSON-событиями."""
    return ["opencode", "run", "-m", model, "--format", "json", brief]


def display_command(argv: Sequence[str]) -> str:
    """Короткая печатная форма команды `opencode run` (бриф сокращён до первой строки)."""
    brief = argv[-1].splitlines()[0] if argv[-1] else ""
    short = brief if len(brief) <= 90 else brief[:87] + "..."
    return f'{" ".join(argv[:-1])} "{short}" < /dev/null'


def round_dir(round_id: str) -> str:
    """Каталог файлов раунда внутри панели."""
    return f"{PANEL_DIR}/{round_id.lower()}"


def seat_file(round_id: str, seat: str) -> str:
    """Путь файла судьи в раунде."""
    return f"{round_dir(round_id)}/{seat}.md"


def hat_for(round_id: str, seat: str) -> str:
    """Шляпа места в раунде по таблице ротации."""
    return HATS[round_id][SEATS.index(seat)]


@dataclass(frozen=True)
class PassInfo:
    """Паспорт прохода Панели, который подставляется в брифы."""

    pass_id: str
    cycle: int
    manifest_sha: str
    freeze_digest: str | None = None
    candidate: str | None = None


PLACEHOLDER_PASS = PassInfo(
    f"{TASK_ID}-c1-<время>", 1, "<manifest_sha256>", "<freeze_sha256>", "<ACCEPT|REJECT>"
)


def judge_header(round_id: str, seat: str, manifest_sha: str) -> str:
    """Заголовок файла судьи (первые пять строк ответа)."""
    return "\n".join(
        (
            f"SEAT: {seat}",
            f"ROUND: {round_id}",
            f"HAT: {hat_for(round_id, seat)}",
            f"PROCEDURE_ACCEPTED: {manifest_sha}",
            "ORIGIN: live",
        )
    )


def previous_round(round_id: str) -> str | None:
    """Раунд, ответы которого судья видит в D-раунде."""
    index = DEBATE_ROUNDS.index(round_id) if round_id in DEBATE_ROUNDS else 0
    return DEBATE_ROUNDS[index - 1] if index > 0 else None


def open_finding_ids(ledger_tsv: str) -> list[str]:
    """F-ID находок со статусом OPEN из текста реестра `findings-ledger.tsv`."""
    found: list[str] = []
    for line in ledger_tsv.splitlines()[1:]:
        cells = line.split("\t")
        if len(cells) >= LEDGER_COLUMNS and cells[LEDGER_STATUS_COLUMN] == "OPEN":
            found.append(cells[0])
    return found


def _round_instructions(round_id: str, info: PassInfo, context: str) -> list[str]:
    """Часть брифа, зависящая от раунда: формат тела ответа и входы раунда."""
    if round_id == "R1":
        return [
            "Чужих оценок у тебя нет. Затем строка COVERAGE: 1=OK|ISSUE 2=OK|ISSUE 3=OK|ISSUE "
            "4=OK|ISSUE 5=OK|ISSUE (все пять ключей).",
            "Каждая находка одной строкой: FINDING <id>: <BLOCKER|IMPORTANT|MINOR> | "
            "<файл:строка> | <описание без символа |>. Находка без файла:строки и проверяемого "
            "факта недопустима. Нет находок — строка FINDINGS: none.",
        ]
    if round_id == FINAL_ROUND:
        return [
            "Слепой финал: чужих ответов C1 у тебя нет и искать их не нужно. Новые находки здесь "
            f"не добавляются. Кандидат: {info.candidate or '<кандидат>'}.",
            f"Далее строки: FREEZE_SHA256: {info.freeze_digest or '<digest>'}",
            "VERDICT: ACCEPT или VERDICT: REJECT",
            "OBJECTION: <файл:строка> | <дефект> (обязательна при REJECT против кандидата ACCEPT)",
            "FALLBACK_CONSENT: YES (согласие на общий REJECT, если единого ACCEPT не будет)",
            f"Пакет (дословные копии):\n{context}",
        ]
    ledger = context.partition(LEDGER_MARKER)[2].partition("\n###")[0]
    open_ids = ", ".join(open_finding_ids(ledger)) or "открытых находок нет"
    return [
        "Пересмотри открытые находки с новой шляпой. Тело ответа: секция "
        "«## Ответы на вопросы коллег»; по одной строке POSITION F-NNN: "
        "AGREE|DISPUTE|AMEND|WITHDRAW|INCONCLUSIVE | evidence: ... либо ARG: ... либо NEW: ... "
        "на каждую открытую находку (смена своей позиции только с ARG: или NEW:; AMEND только "
        "автору, с severity=<BLOCKER|IMPORTANT|MINOR>); необязательно NEW-FINDING <id>: "
        "<SEV> | <файл:строка> | <описание>; секция «## Вопросы коллегам (к следующему раунду)»"
        + (
            " — в D3 только «вопросов нет»."
            if round_id == "D3"
            else ": вопросы или «вопросов нет»."
        ),
        f"Открытые находки, по которым нужна позиция: {open_ids}.",
        f"Дословные копии реестра и ответов прошлого раунда:\n{context}",
    ]


def build_judge_brief(round_id: str, seat: str, info: PassInfo, context: str = "") -> str:
    """Бриф судьи: ссылка на скилл панели, входы, точный формат ответа раунда.

    `context` — дословные копии входов раунда (реестр и ответы прошлого раунда в D, пакет
    с реестром и `freeze.json` в C1); их читает с диска и подставляет Оркестратор.
    """
    hat = hat_for(round_id, seat)
    lines = [
        f"Ты {seat} Панели техлидов, раунд {round_id}, шляпа {hat} ({HAT_FOCUS[hat]}).",
        f"Проход {info.pass_id}, задача {TASK_ID}, цикл {info.cycle}.",
        f"Выполни процедуру {PANEL_SKILL}; формат и правила раунда — {CONSENSUS_DOC}.",
        "Режим STRICT READ-ONLY: ничего не правь, не создавай файлов, не запускай команд "
        "с побочными эффектами. Ответ — только текст в stdout.",
        f"Входы (читай сам): спека {SPEC}; риск-план {RISK_PLAN}; рубрика {RUBRIC}; "
        f"handoff Кодера {HANDOFF_MD}; свидетельство CODE_GATE {CODE_GATE_JSON}; "
        f"diff: {DIFF_COMMAND}. Проверь все 5 критериев рубрики.",
        "Первые пять строк ответа ровно такие:",
        judge_header(round_id, seat, info.manifest_sha),
        *_round_instructions(round_id, info, context),
    ]
    return "\n".join(lines)


def build_coder_brief(cycle: int, rework_input: str | None = None) -> str:
    """Бриф Кодера: Цикл 1 — скилл `feature`, Циклы 2..5 — скилл `rework`."""
    number = f"{cycle:02d}"
    outputs = (
        f"Результат: handoff/coder-{number}.json (schema_version 1.1) и {HANDOFF_MD} "
        "(заголовок «# Handoff Кодер → Панель техлидов», разделы «Команды и коды выхода», "
        "«Решения», «Риски», «Не смотрел»). Запусти проверки сам и приведи коды выхода."
    )
    common = (
        f"Задача {TASK_ID}, цикл {cycle}. Спека {SPEC}, риск-план {RISK_PLAN}; "
        "Blast Radius — раздел 1 спеки; роль и ограничения — prompts/01-coder.md."
    )
    if cycle == 1 or rework_input is None:
        return "\n".join((f"Ты Кодер. Выполни процедуру {FEATURE_SKILL}.", common, outputs))
    return "\n".join(
        (
            f"Ты Кодер. Выполни процедуру {REWORK_SKILL}.",
            common,
            f"Вход доработки: {rework_input} (инструкции RW-NNN либо CG-NNN). "
            "Исправь только перечисленное, замечаний вне брифа не изобретай. "
            f"В handoff добавь rw_trace по каждому RW-NNN. {outputs}",
        )
    )


def build_rework_brief_prompt(
    info: PassInfo, next_cycle: int, ledger_hash: str, inputs: str
) -> str:
    """Бриф функции `panel-rework-summarizer`: свежий read-only процесс, один JSON в stdout.

    `inputs` — дословные копии входов (`ledger`, `r1`, `d1`, `d2`, `d3`, `c1`, `freeze`, `diff`),
    функция сама на диске ничего не ищет.
    """
    return "\n".join(
        (
            f"Ты функция panel-rework-summarizer (процедура {PANEL_SKILL}, схема "
            f"{REWORK_BRIEF_SCHEMA}). STRICT READ-ONLY: ничего не правь и не создавай.",
            "Входы даны ниже дословно: ledger, r1, d1, d2, d3, c1, freeze, diff. Ничего не ищи "
            "на диске. Нет обязательного входа — единственная строка stdout: ASK: <имя входа>.",
            "Переведи согласованные находки реестра в один JSON-объект по схеме. Каждый F-ID "
            "реестра — ровно в одну корзину: instructions, non_blocking_followups или excluded. "
            "Не изобретай исправлений, не меняй тяжесть, не склеивай разные причины, не отсеивай "
            "находки. Выведи только JSON-объект; Оркестратор запишет "
            f"{REWORK_BRIEF} и проверит его.",
            f"Параметры: task_id {TASK_ID}, cycle {next_cycle} (цикл, который получит Кодер), "
            f"source_pass_id {info.pass_id}, ledger_hash {ledger_hash}.",
            inputs,
        )
    )


@dataclass(frozen=True)
class PlannedCall:
    """Один запланированный вызов `opencode run`."""

    label: str
    argv: list[str]


def plan_cycle_calls(
    cycle: int, model: str, info: PassInfo = PLACEHOLDER_PASS
) -> list[PlannedCall]:
    """Последовательность вызовов одного цикла: Кодер, затем 15 вызовов панели."""
    mode = "feature" if cycle == 1 else "rework"
    rework_input = REWORK_BRIEF if cycle > 1 else None
    calls = [
        PlannedCall(
            f"цикл {cycle}: Кодер ({mode})",
            build_opencode_command(model, build_coder_brief(cycle, rework_input)),
        )
    ]
    for round_id in (*DEBATE_ROUNDS, FINAL_ROUND):
        for seat in SEATS:
            brief = build_judge_brief(round_id, seat, info, "<входы раунда>")
            calls.append(
                PlannedCall(
                    f"цикл {cycle}: {round_id} {seat} ({hat_for(round_id, seat)})",
                    build_opencode_command(model, brief),
                )
            )
    return calls


def plan_rework_call(cycle: int, model: str) -> PlannedCall:
    """Вызов функции `panel-rework-summarizer` после согласованного REJECT."""
    brief = build_rework_brief_prompt(PLACEHOLDER_PASS, cycle + 1, "<ledger_sha256>", "<входы>")
    return PlannedCall(
        f"цикл {cycle}: panel-rework-summarizer", build_opencode_command(model, brief)
    )


def print_dry_run(model: str, max_cycles: int) -> None:
    """Напечатать последовательность команд без запуска процессов."""
    print(f"DRY-RUN: модель {model}, до {max_cycles} циклов; процессы не запускаются.")
    for call in plan_cycle_calls(1, model):
        print(f"{call.label}\n  {display_command(call.argv)}")
    print("при согласованном REJECT:")
    rework = plan_rework_call(1, model)
    print(f"{rework.label}\n  {display_command(rework.argv)}")
    if max_cycles > 1:
        coder = plan_cycle_calls(2, model)[0]
        print(f"{coder.label}\n  {display_command(coder.argv)}")
        print(f"циклы 3..{max_cycles}: тот же порядок; после потолка циклов — ESCALATE")


# --------------------------------------------------------------------------------------
# Разбор вывода opencode
# --------------------------------------------------------------------------------------


def extract_text(raw: str) -> str:
    """Текст ответа: JSON-события OpenCode склеиваются, обычный текст возвращается как есть.

    Идея та же, что в `.agents/scripts/extract_opencode_text.py`: берутся события
    `type == "text"`, событие уровня сессии `error` делает ответ непригодным.
    """
    cleaned = ANSI_ESCAPE.sub("", raw).strip()
    events: list[dict[str, object]] = []
    for line in cleaned.splitlines():
        if not line.strip():
            continue
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError:
            return cleaned
        if not isinstance(parsed, dict) or "type" not in parsed:
            return cleaned
        events.append(cast(dict[str, object], parsed))
    if not events:
        return ""
    parts: list[str] = []
    for event in events:
        kind = event.get("type")
        if isinstance(kind, str) and kind in FATAL_EVENT_TYPES:
            return ""
        part = event.get("part")
        if kind == "text" and isinstance(part, dict):
            text = cast(dict[str, object], part).get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
    return "\n".join(parts).strip()


def trim_to_header(text: str) -> str:
    """Отрезать вступление и завершающий ограждающий блок: файл судьи начинается с `SEAT:`."""
    match = HEADER_START.search(text)
    body = text[match.start() :] if match else text
    lines = body.rstrip().splitlines()
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def find_last_json_object(text: str) -> dict[str, object] | None:
    """Последний валидный JSON-объект в тексте; пояснения вокруг допустимы."""
    decoder = json.JSONDecoder()
    for index in range(len(text) - 1, -1, -1):
        if text[index] != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
    return None


def last_hex(text: str) -> str | None:
    """Последний sha256 (64 hex-символа) в выводе помощника."""
    found = HEX64.findall(text)
    return found[-1] if found else None


def parse_verdict(stdout: str) -> str | None:
    """Вердикт из последней непустой строки вывода `generate_proof.py`."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    match = VERDICT_LINE.match(lines[-1])
    return match.group(1) if match else None


# --------------------------------------------------------------------------------------
# CODE_GATE: настоящие команды и свидетельство
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GateStep:
    """Шаг CODE_GATE: каноническая команда (для свидетельства) и аргументы запуска."""

    label: str
    argv: tuple[str, ...]
    needs_db: bool = False


@dataclass(frozen=True)
class GateResult:
    """Код выхода шага CODE_GATE."""

    label: str
    exit_code: int
    tail: str = ""


def gate_steps() -> list[GateStep]:
    """Шаги CODE_GATE; команды идут в интерпретаторе проекта, подпись — как `uv run ...`."""
    py = sys.executable
    return [
        GateStep("uv run ruff check .", (py, "-m", "ruff", "check", ".")),
        GateStep("uv run ruff format --check .", (py, "-m", "ruff", "format", "--check", ".")),
        GateStep("uv run basedpyright", (py, "-m", "basedpyright")),
        GateStep("uv run pytest -q", (py, "-m", "pytest", "-q", "-p", "no:cacheprovider")),
        GateStep("uv run alembic upgrade head", (py, "-m", "alembic", "upgrade", "head"), True),
        GateStep("uv run alembic check", (py, "-m", "alembic", "check"), True),
        GateStep(
            "uv run pytest scripts -q",
            (py, "-m", "pytest", "scripts", "-q", "-p", "no:cacheprovider"),
        ),
        GateStep(BLAST_STEP_LABEL, (py, "scripts/orchestrate_pipeline.py", "--check-blast-radius")),
        GateStep("uv run python scripts/mutate_probe.py", (py, "scripts/mutate_probe.py")),
    ]


def _run_step(root: Path, step: GateStep, env: Mapping[str, str] | None) -> GateResult:
    result = make_runner(root, env if step.needs_db else None, GATE_TIMEOUT_S)(step.argv)
    return GateResult(step.label, result.returncode, tail(result.stdout + result.stderr))


def _run_chain(root: Path, steps: Sequence[GateStep], env: Mapping[str, str]) -> list[GateResult]:
    """Шаги с общей БД: по порядку, после первой ошибки остальные не запускаются."""
    results: list[GateResult] = []
    for step in steps:
        results.append(_run_step(root, step, env))
        if results[-1].exit_code != 0:
            break
    return results


def run_gate_commands(root: Path) -> list[GateResult]:
    """Выполнить CODE_GATE: проверки на чтение параллельно, мутационная проба — последней.

    Результаты возвращаются в порядке `gate_steps()`; шаги, не запущенные из-за ошибки
    предыдущего в цепочке миграций, получают код 125.
    """
    steps = gate_steps()
    by_label = {step.label: step for step in steps}
    with tempfile.TemporaryDirectory(prefix="linksvc-alembic-") as tmp:
        env = {"DATABASE_URL": f"sqlite+aiosqlite:///{Path(tmp) / 'migrate.db'}"}
        chain = [by_label["uv run alembic upgrade head"], by_label["uv run alembic check"]]
        parallel = [
            step for step in steps if not step.needs_db and "mutate_probe" not in step.label
        ]
        done: dict[str, GateResult] = {}
        with ThreadPoolExecutor(max_workers=len(parallel) + 1) as pool:
            chain_future = pool.submit(_run_chain, root, chain, env)
            futures = [pool.submit(_run_step, root, step, None) for step in parallel]
            for future in futures:
                result = future.result()
                done[result.label] = result
            for result in chain_future.result():
                done[result.label] = result
        probe = by_label["uv run python scripts/mutate_probe.py"]
        done[probe.label] = _run_step(root, probe, None)
    return [done.get(step.label, GateResult(step.label, 125, "не запускался")) for step in steps]


def allowed_paths(root: Path) -> list[str]:
    """Разрешённые для изменения пути из раздела Blast Radius спеки (каталоги — с `/` на конце)."""
    text = (root / SPEC).read_text(encoding="utf-8")
    section = text.partition(ALLOWED_HEADING)[2].partition(FORBIDDEN_HEADING)[0]
    return [token for token in PATH_TOKEN.findall(section) if "/" in token or "." in token]


def _git_lines(runner: Runner, args: Sequence[str]) -> list[str] | None:
    """Строки вывода `git` (пути относительно корня проекта); `None` — команда не удалась."""
    result = runner(["git", "-c", "core.quotepath=false", *args])
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


def changed_paths(root: Path, pathspec: Sequence[str], *, vs_base: bool) -> set[str] | None:
    """Изменённые пути: рабочее дерево против HEAD, новые файлы и (`vs_base`) ветка против main."""
    runner = make_runner(root, timeout=GIT_TIMEOUT_S)
    tracked = _git_lines(runner, ["diff", "--name-only", "--relative", "HEAD", "--", *pathspec])
    fresh = _git_lines(runner, ["ls-files", "--others", "--exclude-standard", "--", *pathspec])
    if tracked is None or fresh is None:
        return None
    if not vs_base:
        return {*tracked, *fresh}
    base = f"{BASE_REF}...HEAD"
    branch = _git_lines(runner, ["diff", "--name-only", "--relative", base, "--", *pathspec])
    return None if branch is None else {*tracked, *fresh, *branch}


def _is_allowed(path: str, allowed: Sequence[str]) -> bool:
    """Путь совпадает с разрешённым файлом или лежит в разрешённом каталоге."""
    return any(path == item or (item.endswith("/") and path.startswith(item)) for item in allowed)


def _protected_hash_mismatches(root: Path) -> set[str]:
    """Защищённые файлы, содержимое которых (даже закоммиченное) не равно эталонному sha256."""
    return {
        name
        for name, expected in PROTECTED_FILE_SHA256.items()
        if ((sha256_of(root / name) if (root / name).is_file() else None) != expected)
    }


def check_blast_radius(root: Path) -> list[str]:
    """Механический Blast Radius: защищённые файлы нетронуты, правки продукта — в allowed_paths."""
    try:
        allowed = allowed_paths(root)
    except OSError as error:
        return [f"{SPEC}: не читается ({error.__class__.__name__})"]
    if not allowed:
        return [f"{SPEC}: нет списка разрешённых файлов в разделе Blast Radius"]
    protected = changed_paths(root, PROTECTED_FILES, vs_base=False)
    if protected is None:
        return ["git недоступен: Blast Radius проверить нельзя"]
    product = changed_paths(root, PRODUCT_PATHS, vs_base=True)
    if product is None:
        return ["не удалось определить изменения относительно базовой ветки (fail-closed)"]
    protected |= _protected_hash_mismatches(root)
    errors = [f"защищённый файл изменён: {name}" for name in sorted(protected)]
    errors += [
        f"файл вне разрешённого списка спеки: {name}"
        for name in sorted(product)
        if not _is_allowed(name, allowed)
    ]
    return errors


def input_bindings(root: Path) -> dict[str, str]:
    """Привязка свидетельства к sha256 входов: спека, риск-план, handoff Кодера."""
    return {
        "coder_handoff": sha256_of(root / HANDOFF_MD),
        "risk_plan": sha256_of(root / RISK_PLAN),
        "spec": sha256_of(root / SPEC),
    }


def render_code_gate(
    root: Path, results: Sequence[GateResult], cycle: int, source: str
) -> dict[str, object]:
    """Содержимое `.ai-team/code-gate.json`."""
    return {
        "commands": [{"cmd": item.label, "exit_code": item.exit_code} for item in results],
        "cycle": cycle,
        "inputs_sha256": input_bindings(root),
        "source": source,
        "task_id": TASK_ID,
    }


def gate_summary(data: Mapping[str, object]) -> tuple[bool, object]:
    """Суть свидетельства: все обязательные команды зелёные + привязки входов."""
    commands = data.get("commands")
    green = isinstance(commands, list) and not gate_errors_in_commands(cast(list[object], commands))
    return green, data.get("inputs_sha256")


def gate_errors_in_commands(commands: Sequence[object]) -> list[str]:
    """Замечания к списку команд свидетельства: нет обязательной или код не 0."""
    pairs: list[tuple[str, object]] = []
    for item in commands:
        if isinstance(item, dict):
            mapping = cast(dict[str, object], item)
            pairs.append((str(mapping.get("cmd", "")), mapping.get("exit_code")))
    errors = [
        f"нет обязательной команды `{need}`"
        for need in GATE_REQUIRED
        if not any(need in cmd for cmd, _ in pairs)
    ]
    errors += [f"`{cmd}` вернула {code!r}, нужен 0" for cmd, code in pairs if code != 0]
    return errors


def write_code_gate(
    root: Path, results: Sequence[GateResult], cycle: int, journal: Journal
) -> None:
    """Записать свидетельство; живой прогон, совпавший по существу с имеющимся, не перезаписывает его."""
    path = root / CODE_GATE_JSON
    fresh = render_code_gate(root, results, cycle, "live")
    if path.is_file():
        try:
            old: object = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = None
        if isinstance(old, dict):
            old_map = cast(dict[str, object], old)
            if gate_summary(old_map) == gate_summary(fresh) and gate_summary(fresh)[0]:
                journal.write("CODE_GATE: живой прогон зелёный и совпал с имеющимся свидетельством")
                return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(fresh, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    journal.write(f"CODE_GATE: свидетельство записано в {CODE_GATE_JSON} (source=live)")


def run_code_gate(root: Path, cycle: int, journal: Journal) -> list[GateResult]:
    """Настоящий CODE_GATE: прогон команд и запись свидетельства; возвращает красные шаги."""
    results = run_gate_commands(root)
    for item in results:
        journal.write(f"{item.label}: код возврата {item.exit_code}")
        if item.exit_code != 0:
            journal.write(f"{item.label}: вывод (хвост):\n{item.tail}")
    write_code_gate(root, results, cycle, journal)
    return [item for item in results if item.exit_code != 0]


def check_code_gate(root: Path) -> list[str]:
    """Быстрая проверка свидетельства: обязательные команды, коды выхода, привязка входов."""
    path = root / CODE_GATE_JSON
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{CODE_GATE_JSON}: не читается ({error})"]
    if not isinstance(data, dict):
        return [f"{CODE_GATE_JSON}: корень не объект"]
    mapping = cast(dict[str, object], data)
    commands = mapping.get("commands")
    if not isinstance(commands, list):
        return [f"{CODE_GATE_JSON}: нет списка commands"]
    errors = gate_errors_in_commands(cast(list[object], commands))
    bound = mapping.get("inputs_sha256")
    if not isinstance(bound, dict):
        return [*errors, f"{CODE_GATE_JSON}: нет inputs_sha256"]
    current = input_bindings(root)
    bound_map = cast(dict[str, object], bound)
    errors += [
        f"устарел вход {name}: хеш в свидетельстве не совпал с файлом"
        for name, value in current.items()
        if bound_map.get(name) != value
    ]
    return errors


# --------------------------------------------------------------------------------------
# Быстрый детерминированный режим
# --------------------------------------------------------------------------------------


def helper_command(root: Path, args: Sequence[str]) -> list[str]:
    """Команда детерминированного помощника `scripts/generate_proof.py`."""
    return [sys.executable, str(root / "scripts" / "generate_proof.py"), *args]


def verify_panel(root: Path, runner: Runner, journal: Journal) -> tuple[str | None, str]:
    """Итоговая проверка пакета (пишет verdict.md и consensus-proof.json): вердикт и вывод."""
    result = runner(helper_command(root, []))
    output = (result.stdout + result.stderr).strip()
    verdict = parse_verdict(result.stdout)
    journal.write(f"generate_proof: код возврата {result.returncode}, вердикт {verdict}")
    if verdict is None or VERDICT_EXIT[verdict] != result.returncode:
        journal.write(f"generate_proof: вывод (хвост):\n{tail(output)}")
        return None, output
    return verdict, output


def finish(verdict: str, detail: str = "") -> int:
    """Напечатать итог и вернуть код выхода: последней строкой всегда `VERDICT: ...`."""
    if verdict == "READY":
        print("GATE: PASS")
    elif verdict == "REJECT":
        print("GATE: REWORK" + (f". {detail}" if detail else ""))
    else:
        print("GATE: BLOCKED" + (f". {detail}" if detail else ""))
    print(f"VERDICT: {verdict}")
    return VERDICT_EXIT[verdict]


def fail(step: str) -> int:
    """Красный шаг: `VERDICT: FAIL (<шаг>)` и код 1."""
    print(f"VERDICT: FAIL ({step})")
    return 1


def run_fast(root: Path, journal: Journal, run_gates: bool = False) -> int:
    """Быстрая проверка пакета; `run_gates` предварительно выполняет настоящий CODE_GATE."""
    journal.reset("ЖУРНАЛ ИСПОЛНЕНИЯ ПРОВЕРКИ LINK-42")
    journal.write("ЭТАП 1: наличие артефактов")
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        journal.write(f"артефакты отсутствуют: {missing}")
        return fail("artifacts")
    if run_gates:
        journal.write("ЭТАП 2: CODE_GATE, настоящие команды")
        cycle = _existing_cycle(root)
        red = run_code_gate(root, cycle, journal)
        if red:
            return fail(red[0].label)
    journal.write("ЭТАП 3: handoff Кодера")
    errors = validate_handoff.validate_path(root / HANDOFF_MD)
    if errors:
        for error in errors:
            journal.write(f"handoff Кодера: {error}")
        return fail("handoff-coder")
    journal.write("ЭТАП 4: свидетельство CODE_GATE")
    errors = check_code_gate(root)
    if errors:
        for error in errors:
            journal.write(f"CODE_GATE: {error}")
        return fail("code-gate")
    journal.write("ЭТАП 5: Панель техлидов, проверка консенсуса")
    verdict, output = verify_panel(root, make_runner(root), journal)
    if verdict is None:
        return fail("generate_proof")
    if verdict == "READY":
        journal.write("ПАКЕТ ПРИНЯТ: все шаги вернули 0")
        return finish("READY")
    reason = _first_reason(output)
    journal.write(f"ПАНЕЛЬ: {verdict}. {reason}")
    return finish(verdict, reason)


def _first_reason(output: str) -> str:
    """Первая содержательная строка вывода помощника (причина исхода)."""
    for line in output.splitlines():
        text = line.strip()
        if text and not VERDICT_LINE.match(text):
            return text
    return ""


def _existing_cycle(root: Path) -> int:
    """Номер цикла из имеющегося свидетельства; без него — 1."""
    try:
        data: object = json.loads((root / CODE_GATE_JSON).read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return 1
    if isinstance(data, dict):
        cycle = cast(dict[str, object], data).get("cycle")
        if isinstance(cycle, int) and cycle > 0:
            return cycle
    return 1


# --------------------------------------------------------------------------------------
# Живой внешний цикл
# --------------------------------------------------------------------------------------


@dataclass
class LiveDeps:
    """Внешние точки живого цикла; в тестах заменяются на заглушки."""

    runner: Runner
    validate: Callable[[Path], list[str]]
    code_gate: Callable[[Path, int, Journal], list[GateResult]]


@dataclass
class LiveContext:
    """Состояние живого прохода."""

    root: Path
    model: str
    max_cycles: int
    journal: Journal
    deps: LiveDeps
    started: int = field(default_factory=lambda: int(time.time()))
    last_pass: PassInfo | None = None


def invoke_opencode(ctx: LiveContext, label: str, brief: str, attempts: int) -> str | None:
    """Один логический вызов: до `attempts` свежих процессов; текст ответа или `None`."""
    argv = build_opencode_command(ctx.model, brief)
    for attempt in range(1, attempts + 1):
        began = time.monotonic()
        result = ctx.deps.runner(argv)
        text = extract_text(result.stdout) if result.returncode == 0 else ""
        ctx.journal.write(
            f"{label}: попытка {attempt}, код {result.returncode}, "
            f"{time.monotonic() - began:.0f} с, ответ {len(text)} симв."
        )
        if text:
            return text
        _keep_failed_attempt(ctx, label, attempt, result)
    return None


def _keep_failed_attempt(ctx: LiveContext, label: str, attempt: int, result: RunResult) -> None:
    """Исходная неудачная попытка сохраняется рядом с журналом."""
    safe = re.sub(r"[^0-9A-Za-zА-Яа-я_-]+", "_", label)
    target = ctx.root / "handoff" / "attempts" / f"{safe}.attempt{attempt}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"returncode={result.returncode}\n--- stdout\n{result.stdout}\n--- stderr\n{result.stderr}\n",
        encoding="utf-8",
    )


def helper_value(ctx: LiveContext, args: Sequence[str]) -> str | None:
    """Вызов помощника `generate_proof.py <подкоманда>`: sha256 из вывода или `None`."""
    result = ctx.deps.runner(helper_command(ctx.root, args))
    value = last_hex(result.stdout)
    ctx.journal.write(f"generate_proof {' '.join(args[:1])}: код {result.returncode}")
    if result.returncode != 0 or value is None:
        ctx.journal.write(f"generate_proof {args[0]}: вывод (хвост):\n{tail(result.stdout)}")
        ctx.journal.write(tail(result.stderr))
        return None
    return value


def archive_panel(ctx: LiveContext, cycle: int) -> None:
    """Файлы прошлого прохода уходят в `handoff/panel-archive/`, чтобы не смешиваться с новым."""
    panel = ctx.root / PANEL_DIR
    if not panel.is_dir() or not any(panel.iterdir()):
        return
    target = ctx.root / "handoff" / "panel-archive" / f"before-cycle-{cycle}-{ctx.started}"
    target.mkdir(parents=True, exist_ok=True)
    for entry in panel.iterdir():
        shutil.move(str(entry), str(target / entry.name))
    ctx.journal.write(f"прошлый проход панели перенесён в {target.relative_to(ctx.root)}")


def file_block(root: Path, relative: str) -> str:
    """Дословная копия файла для брифа; нет файла — явная пометка (функция ответит `ASK:`)."""
    path = root / relative
    body = path.read_text(encoding="utf-8").rstrip("\n") if path.is_file() else "(файла нет)"
    return f"### {relative}\n{body}\n"


def round_context(root: Path, round_id: str) -> str:
    """Входы раунда: реестр и ответы прошлого раунда (D) либо реестр и `freeze.json` (C1)."""
    blocks = [file_block(root, LEDGER_TSV)]
    if round_id == FINAL_ROUND:
        blocks.append(file_block(root, FREEZE_JSON))
    elif (previous := previous_round(round_id)) is not None:
        blocks += [file_block(root, seat_file(previous, seat)) for seat in SEATS]
    return "\n".join(blocks)


def git_diff(ctx: LiveContext) -> str:
    """Дифф продуктовых путей ветки относительно main; длинный дифф обрезается с пометкой."""
    result = ctx.deps.runner(["git", "diff", f"{BASE_REF}...HEAD", "--", *PRODUCT_PATHS])
    if result.returncode != 0 or not result.stdout.strip():
        return "(diff недоступен)"
    if len(result.stdout) > DIFF_LIMIT:
        return result.stdout[:DIFF_LIMIT] + "\n(diff обрезан)"
    return result.stdout


def rework_inputs(ctx: LiveContext) -> str:
    """Входы функции `panel-rework-summarizer`: ledger, r1, d1, d2, d3, c1, freeze, diff."""
    blocks = [file_block(ctx.root, LEDGER_TSV)]
    for round_id in (*DEBATE_ROUNDS, FINAL_ROUND):
        blocks += [file_block(ctx.root, seat_file(round_id, seat)) for seat in SEATS]
    blocks.append(file_block(ctx.root, FREEZE_JSON))
    blocks.append(f"### diff ({DIFF_COMMAND})\n{git_diff(ctx)}\n")
    return "\n".join(blocks)


def candidate_of(root: Path) -> str | None:
    """Кандидат из `freeze.json` (ACCEPT или REJECT)."""
    try:
        data: object = json.loads((root / FREEZE_JSON).read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        value = cast(dict[str, object], data).get("candidate")
        return value if isinstance(value, str) else None
    return None


def tree_fingerprint(root: Path) -> dict[str, str]:
    """sha256 всех файлов проекта, кроме `.ai-team/`, `handoff/`, `.git`, `.venv` и кэшей."""
    found: dict[str, str] = {}
    for current, dirs, names in os.walk(root):
        base = Path(current)
        top = base == root
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in FINGERPRINT_SKIP_ANY and not (top and name in FINGERPRINT_SKIP_TOP)
        )
        for name in [*dirs, *names]:
            path = base / name
            if path.is_symlink() and path.is_dir():
                target = hashlib.sha256(os.readlink(path).encode()).hexdigest()
                found[path.relative_to(root).as_posix()] = target
            elif path.suffix != ".pyc" and path.is_file():
                found[path.relative_to(root).as_posix()] = sha256_of(path)
    return found


def run_judge(ctx: LiveContext, round_id: str, seat: str, info: PassInfo, context: str) -> bool:
    """Один судья: свежий процесс, ответ сохраняет Оркестратор; не более двух попыток.

    Отпечаток дерева проекта до и после вызова: любая запись вне `.ai-team/` и `handoff/`
    — `JudgeReadOnlyViolationError`.
    """
    brief = build_judge_brief(round_id, seat, info, context)
    before = tree_fingerprint(ctx.root)
    text = invoke_opencode(ctx, f"{round_id}-{seat}", brief, JUDGE_ATTEMPTS)
    after = tree_fingerprint(ctx.root)
    if after != before:
        touched = sorted(name for name in {*before, *after} if before.get(name) != after.get(name))
        raise JudgeReadOnlyViolationError(
            f"{round_id}-{seat} изменил файлы в режиме read-only: {', '.join(touched)}"
        )
    if text is None:
        return False
    target = ctx.root / seat_file(round_id, seat)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(trim_to_header(text) + "\n", encoding="utf-8")
    return True


def run_round(ctx: LiveContext, round_id: str, info: PassInfo) -> bool:
    """Три судьи раунда параллельно; кворум 3/3 или `False`."""
    ctx.journal.write(f"РАУНД {round_id}: три параллельных процесса")
    context = "" if round_id == "R1" else round_context(ctx.root, round_id)
    with ThreadPoolExecutor(max_workers=len(SEATS)) as pool:
        futures = [pool.submit(run_judge, ctx, round_id, seat, info, context) for seat in SEATS]
        outcomes = [future.result() for future in futures]
    return all(outcomes)


def run_panel(ctx: LiveContext, cycle: int) -> tuple[str, str]:
    """Один проход панели: INIT → R1 → D1 → D2 → D3 → FREEZE → C1; вердикт и причина."""
    archive_panel(ctx, cycle)
    pass_id = f"{TASK_ID}-c{cycle}-{ctx.started}"
    manifest_sha = helper_value(
        ctx,
        ["manifest", ".ai-team", "--model", ctx.model, "--cycle", str(cycle), "--pass-id", pass_id],
    )
    if manifest_sha is None:
        return "ESCALATE", "не удалось собрать manifest.json"
    info = PassInfo(pass_id, cycle, manifest_sha)
    ctx.last_pass = info
    for round_id in DEBATE_ROUNDS:
        if not run_round(ctx, round_id, info):
            return _technical(ctx, "QUORUM_UNAVAILABLE", f"нет ответа судьи в раунде {round_id}")
        if helper_value(ctx, ["ledger", ".ai-team"]) is None:
            return _technical(ctx, "CONSENSUS_UNAVAILABLE", f"реестр не собран после {round_id}")
    digest = helper_value(ctx, ["freeze", ".ai-team"])
    if digest is None:
        return _technical(ctx, "CONSENSUS_UNAVAILABLE", "freeze.json не собран")
    final = PassInfo(pass_id, cycle, manifest_sha, digest, candidate_of(ctx.root))
    if not run_round(ctx, FINAL_ROUND, final):
        return _technical(ctx, "QUORUM_UNAVAILABLE", "нет ответа судьи в раунде C1")
    verdict, output = verify_panel(ctx.root, ctx.deps.runner, ctx.journal)
    if verdict is None:
        return "ESCALATE", "generate_proof не вернул вердикт"
    return verdict, _first_reason(output)


def _technical(ctx: LiveContext, status: str, reason: str) -> tuple[str, str]:
    """Технический исход: записать артефакты проверкой и эскалировать."""
    ctx.journal.write(f"ТЕХНИЧЕСКИЙ ИСХОД {status}: {reason}")
    verify_panel(ctx.root, ctx.deps.runner, ctx.journal)
    return "ESCALATE", f"{status}: {reason}"


def run_coder(ctx: LiveContext, cycle: int, rework_input: str | None) -> bool:
    """Кодер текущего цикла: один свежий процесс, один повтор при транспортном сбое."""
    mode = "feature" if cycle == 1 else "rework"
    text = invoke_opencode(
        ctx, f"coder-{cycle:02d}-{mode}", build_coder_brief(cycle, rework_input), 2
    )
    return text is not None


def coder_failures(ctx: LiveContext, cycle: int) -> list[GateResult]:
    """Замечания к выходу Кодера: handoff-файлы должны пройти валидацию."""
    failures: list[GateResult] = []
    for relative in (f"handoff/coder-{cycle:02d}.json", HANDOFF_MD):
        path = ctx.root / relative
        errors = ctx.deps.validate(path) if path.is_file() else [f"{relative}: файла нет"]
        if errors:
            failures.append(GateResult(f"validate_handoff {relative}", 1, "; ".join(errors)))
    return failures


def write_gate_failure_brief(ctx: LiveContext, next_cycle: int, red: Sequence[GateResult]) -> None:
    """Механический бриф доработки после красного CODE_GATE: `CG-NNN` по красным шагам."""
    data = {
        "failures": [
            {
                "command": item.label,
                "exit_code": item.exit_code,
                "id": f"CG-{number:03d}",
                "output_tail": item.tail,
            }
            for number, item in enumerate(red, start=1)
        ],
        "schema_version": "1.0",
        "source": "code-gate",
        "task_id": TASK_ID,
        "cycle": next_cycle,
    }
    target = ctx.root / GATE_FAILURE_BRIEF
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_rework_brief(ctx: LiveContext, cycle: int) -> str | None:
    """Функция `panel-rework-summarizer`: бриф для Кодера; `None`, если получить его нельзя."""
    label = f"panel-rework-summarizer-c{cycle}"
    ledger = ctx.root / LEDGER_TSV
    ledger_hash = sha256_of(ledger) if ledger.is_file() else "(нет реестра)"
    info = ctx.last_pass or PassInfo(f"{TASK_ID}-c{cycle}", cycle, "")
    brief = build_rework_brief_prompt(info, cycle + 1, ledger_hash, rework_inputs(ctx))
    for attempt in range(1, JUDGE_ATTEMPTS + 1):
        text = invoke_opencode(ctx, label, brief, 1)
        if text is None:
            continue
        if text.lstrip().startswith("ASK:"):
            ctx.journal.write(f"{label}: {text.strip().splitlines()[0]}")
            return None
        payload = find_last_json_object(text)
        if payload is None:
            ctx.journal.write(f"{label}: попытка {attempt}, в ответе нет JSON-объекта")
            continue
        target = ctx.root / REWORK_BRIEF
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
        errors = ctx.deps.validate(target)
        if not errors:
            instructions = payload.get("instructions")
            count = len(cast(list[object], instructions)) if isinstance(instructions, list) else 0
            ctx.journal.write(f"{label}: VALID n_instructions={count}")
            return REWORK_BRIEF
        ctx.journal.write(f"{label}: бриф не прошёл validate_handoff: {errors}")
    return None


def run_live(ctx: LiveContext) -> int:
    """Внешний цикл до `max_cycles` циклов; потолок или технический исход — ESCALATE."""
    ctx.journal.reset("ЖУРНАЛ ЖИВОГО ЦИКЛА LINK-42")
    ctx.journal.write(f"модель {ctx.model}, потолок {ctx.max_cycles} циклов")
    rework_input: str | None = None
    for cycle in range(1, ctx.max_cycles + 1):
        ctx.journal.write(f"ЦИКЛ {cycle}: Кодер")
        if not run_coder(ctx, cycle, rework_input):
            return finish("ESCALATE", f"Кодер цикла {cycle} недоступен")
        red = coder_failures(ctx, cycle)
        if not red:
            ctx.journal.write(f"ЦИКЛ {cycle}: CODE_GATE")
            red = ctx.deps.code_gate(ctx.root, cycle, ctx.journal)
        if red:
            ctx.journal.write(f"ЦИКЛ {cycle}: красный CODE_GATE, панель не запускается")
            write_gate_failure_brief(ctx, cycle + 1, red)
            rework_input = GATE_FAILURE_BRIEF
            continue
        try:
            verdict, reason = run_panel(ctx, cycle)
        except JudgeReadOnlyViolationError as error:
            ctx.journal.write(f"ЦИКЛ {cycle}: нарушение read-only: {error}")
            return finish("ESCALATE", f"нарушение read-only: {error}")
        if verdict == "READY":
            ctx.journal.write(f"ЦИКЛ {cycle}: ACCEPT")
            return finish("READY")
        if verdict == "ESCALATE":
            return finish("ESCALATE", reason)
        ctx.journal.write(f"ЦИКЛ {cycle}: согласованный REJECT")
        if cycle == ctx.max_cycles:
            break
        rework_input = make_rework_brief(ctx, cycle)
        if rework_input is None:
            return finish("ESCALATE", "panel-rework-brief.json не получен")
    return finish("ESCALATE", f"потолок {ctx.max_cycles} циклов исчерпан")


# --------------------------------------------------------------------------------------
# Командная строка
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Options:
    """Разобранные параметры командной строки."""

    run_gates: bool
    live: bool
    dry_run: bool
    model: str
    max_cycles: int
    check_blast_radius: bool = False


def parse_options(argv: Sequence[str] | None, environ: Mapping[str, str]) -> Options:
    """Разобрать аргументы; неверное использование — выход с кодом 2."""
    parser = argparse.ArgumentParser(description="Оркестратор приёмки LINK-42")
    parser.add_argument("--run-gates", action="store_true", help="выполнить настоящий CODE_GATE")
    parser.add_argument("--live", action="store_true", help="внешний цикл через opencode run")
    parser.add_argument("--dry-run", action="store_true", help="с --live: только печать команд")
    parser.add_argument("--model", default=None, help=f"модель (иначе {MODEL_ENV}, иначе default)")
    parser.add_argument("--max-cycles", type=int, default=MAX_CYCLES, help="потолок циклов, 1..5")
    parser.add_argument(
        "--check-blast-radius", action="store_true", help="проверить Blast Radius и выйти"
    )
    args = parser.parse_args(argv)
    run_gates = bool(args.run_gates)
    live = bool(args.live)
    dry_run = bool(args.dry_run)
    max_cycles = cast(int, args.max_cycles)
    if dry_run and not live:
        parser.error("--dry-run допустим только вместе с --live")
    if not 1 <= max_cycles <= MAX_CYCLES:
        parser.error(f"--max-cycles должен быть от 1 до {MAX_CYCLES}")
    try:
        model = resolve_model(cast("str | None", args.model), environ)
    except ValueError as error:
        parser.error(str(error))
    return Options(run_gates, live, dry_run, model, max_cycles, bool(args.check_blast_radius))


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа."""
    options = parse_options(argv, os.environ)
    if options.check_blast_radius:
        problems = check_blast_radius(ROOT)
        for problem in problems:
            print(f"BLAST RADIUS: {problem}")
        print("BLAST RADIUS: " + ("нарушения найдены" if problems else "OK"))
        return 1 if problems else 0
    journal = Journal(ROOT / LOG_RELATIVE)
    if options.live:
        if options.dry_run:
            print_dry_run(options.model, options.max_cycles)
            return 0
        deps = LiveDeps(
            runner=make_runner(ROOT, timeout=OPENCODE_TIMEOUT_S),
            validate=validate_handoff.validate_path,
            code_gate=run_code_gate,
        )
        return run_live(LiveContext(ROOT, options.model, options.max_cycles, journal, deps))
    return run_fast(ROOT, journal, run_gates=options.run_gates)


if __name__ == "__main__":
    sys.exit(main())
