#!/usr/bin/env python3
"""Исполнитель детерминированной механики Панели техлидов (протокол consensus-debate/v1).

Скрипт не судит и не голосует: он только считает то, что считается без модели. Присваивает
сквозные F-ID, собирает реестр находок, считает статусы по позициям судей, хеширует входы,
пишет паспорт прохода и кандидата FREEZE, проверяет слепой финал C1 и выпускает итог.

Подкоманды (первый аргумент):

    sha256 <путь>...                 хеши файлов (один путь: только хеш)
    manifest [team_dir] [--model ID] [--cycle N] [--pass-id S]
    ledger [team_dir]                пересборка findings-ledger.tsv и .md из файлов раундов
    freeze [team_dir]                кандидат FREEZE, печатает digest для C1
    verify [team_dir] [out_path]     проверка всего пакета (режим по умолчанию)

Без подкоманды работает `verify`: `generate_proof.py [team_dir] [out_path]`. Относительные
пути отсчитываются от корня проекта. Код выхода verify: 0 READY, 1 согласованный REJECT,
2 технический исход (ESCALATE). Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

ROOT = Path(__file__).resolve().parent.parent

PROTOCOL = "consensus-debate/v1"
TASK_ID = "LINK-42"
SEATS: tuple[str, ...] = ("judge-1", "judge-2", "judge-3")
ROUNDS: tuple[str, ...] = ("R1", "D1", "D2", "D3", "C1")
DEBATE_ROUNDS: tuple[str, ...] = ("D1", "D2", "D3")
HAT_SKEPTIC = "Скептик"
HAT_REALIST = "Реалист"
HAT_VISIONARY = "Визионер"
HAT_COMMON = "Общая"
ROTATION: dict[str, dict[str, str]] = {
    "R1": {"judge-1": HAT_SKEPTIC, "judge-2": HAT_REALIST, "judge-3": HAT_VISIONARY},
    "D1": {"judge-1": HAT_REALIST, "judge-2": HAT_VISIONARY, "judge-3": HAT_SKEPTIC},
    "D2": {"judge-1": HAT_VISIONARY, "judge-2": HAT_SKEPTIC, "judge-3": HAT_REALIST},
    "D3": {"judge-1": HAT_SKEPTIC, "judge-2": HAT_REALIST, "judge-3": HAT_VISIONARY},
    "C1": {"judge-1": HAT_COMMON, "judge-2": HAT_COMMON, "judge-3": HAT_COMMON},
}
SEVERITIES: tuple[str, ...] = ("BLOCKER", "IMPORTANT", "MINOR")
BLOCKING_SEVERITIES: frozenset[str] = frozenset({"BLOCKER", "IMPORTANT"})
STANCES: tuple[str, ...] = ("AGREE", "DISPUTE", "AMEND", "WITHDRAW", "INCONCLUSIVE")
STATUSES: tuple[str, ...] = ("OPEN", "AGREED", "WITHDRAWN")
ORIGINS: tuple[str, ...] = ("reference-fixture", "live")
CRITERIA: tuple[int, ...] = (1, 2, 3, 4, 5)
CRITERIA_NAMES: dict[int, str] = {
    1: "Спека",
    2: "Diff и Blast Radius",
    3: "Гейты",
    4: "Риск-план и честное «не смотрел»",
    5: "Запреты спеки",
}
CALLS_BUDGET = 15
DEFAULT_MODEL = "opencode/deepseek-v4.1-flash-free"
REQUIRED_COMMANDS: tuple[str, ...] = (
    "ruff check",
    "basedpyright",
    "alembic check",
    "pytest",
    "mutate_probe",
    "check-blast-radius",
)

INPUT_KEYS: tuple[str, ...] = ("spec", "risk_plan", "rubric", "coder_handoff", "code_gate")
CODE_TREE_KEY = "code_tree_sha256"
CODE_TREE_PATHS: tuple[str, ...] = ("app", "tests", "alembic", "pyproject.toml")
CODE_TREE_SKIP_NAMES: frozenset[str] = frozenset({"__pycache__", ".DS_Store"})
SPEC_PATH = "specs/LINK-42-enable-link.md"
RISK_PLAN_PATH = "docs/risk-plan-LINK-42.md"
RUBRIC_PATH = "docs/gate-rubric.md"
DEFAULT_TEAM_DIR = ".ai-team"
DEFAULT_OUT_PATH = "handoff/03-gate-proof.json"
LEDGER_HEADER = "f_id\tseverity\tjudge\tlocation\tsummary\tstatus\tresolution"
LEDGER_COLUMNS = 7
ANSWERS_HEADING = "## Ответы на вопросы коллег"
QUESTIONS_HEADING = "## Вопросы коллегам (к следующему раунду)"
NO_QUESTIONS = "вопросов нет"
LIVE_CHECK_TIMEOUT_SECONDS = 900
STALE_CODE_TREE = (
    "STALE_CODE_TREE: код app/, tests/, alembic/, pyproject.toml изменился после init прохода: "
    "пересоберите manifest и повторите проход"
)

EXIT_READY = 0
EXIT_REJECT = 1
EXIT_ESCALATE = 2

Verdict = Literal["READY", "REJECT", "ESCALATE"]

_ID = r"[A-Za-z0-9_-]+"
_F_ID_RE = re.compile(r"^F-\d{3,}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_LOCATION_RE = re.compile(r"^[^\s|]+:\d+(?:-\d+)?$")
_HEADER_RE = re.compile(r"^([A-Z_]+): (.+)$")
_KIND_RE = re.compile(
    r"^(COVERAGE|FINDINGS|FINDING|EVIDENCE|POSITION|NEW-FINDING"
    r"|FREEZE_SHA256|VERDICT|OBJECTION|FALLBACK_CONSENT)\b"
)
_COVERAGE_RE = re.compile(
    r"^COVERAGE: 1=(OK|ISSUE)\s+2=(OK|ISSUE)\s+3=(OK|ISSUE)\s+4=(OK|ISSUE)\s+5=(OK|ISSUE)$"
)
_FINDING_RE = re.compile(rf"^(?:NEW-)?FINDING ({_ID}): (BLOCKER|IMPORTANT|MINOR) \| (.+)$")
_EVIDENCE_RE = re.compile(r"^EVIDENCE ([1-5]): (.+)$")
_POSITION_RE = re.compile(
    r"^POSITION (F-\d{3,}): (AGREE|DISPUTE|AMEND|WITHDRAW|INCONCLUSIVE)(?: \| (.+))?$"
)
_OBJECTION_RE = re.compile(r"^OBJECTION: (\S+:\d+(?:-\d+)?) \| (.+)$")
_KEY_PREFIXES: tuple[str, ...] = ("severity=", "evidence:", "ARG:", "NEW:")

_ALLOWED_KINDS: dict[str, frozenset[str]] = {
    "R1": frozenset({"COVERAGE", "FINDINGS", "FINDING", "EVIDENCE"}),
    "D": frozenset({"POSITION", "NEW-FINDING"}),
    "C1": frozenset({"FREEZE_SHA256", "VERDICT", "OBJECTION", "FALLBACK_CONSENT"}),
}


class PanelFormatError(ValueError):
    """Файлы раундов или реестр не соответствуют формату протокола."""


@dataclass(frozen=True)
class LedgerRow:
    """Строка реестра находок `findings-ledger.tsv`."""

    f_id: str
    severity: str
    judge: str
    location: str
    summary: str
    status: str
    resolution: str

    def fields(self) -> list[str]:
        """Поля строки в порядке колонок TSV."""
        return [
            self.f_id,
            self.severity,
            self.judge,
            self.location,
            self.summary,
            self.status,
            self.resolution,
        ]


@dataclass(frozen=True)
class FindingLine:
    """Находка из R1 (`FINDING`) или из D (`NEW-FINDING`) до присвоения F-ID."""

    local_id: str
    severity: str
    location: str
    summary: str


@dataclass(frozen=True)
class PositionLine:
    """Строка `POSITION` судьи по одной F-ID."""

    f_id: str
    stance: str
    severity: str | None
    evidence: str
    arg: str
    new: str


@dataclass
class JudgeDoc:
    """Разобранный файл судьи; `errors` — нарушения формата, найденные при разборе."""

    seat: str = ""
    round: str = ""
    hat: str = ""
    procedure: str = ""
    origin: str = ""
    coverage: dict[int, str] = field(default_factory=dict[int, str])
    evidence: dict[int, list[str]] = field(default_factory=dict[int, list[str]])
    findings: list[FindingLine] = field(default_factory=list[FindingLine])
    no_findings: bool = False
    positions: list[PositionLine] = field(default_factory=list[PositionLine])
    new_findings: list[FindingLine] = field(default_factory=list[FindingLine])
    has_answers: bool = False
    has_questions: bool = False
    questions: list[str] = field(default_factory=list[str])
    freeze_sha: str | None = None
    verdict: str | None = None
    objections: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    fallback: bool = False
    errors: list[str] = field(default_factory=list[str])


@dataclass
class PanelDetails:
    """Данные для отчёта `verdict.md` (не входят в хеш-цепочку)."""

    coverage: dict[int, dict[str, str]] = field(default_factory=dict[int, dict[str, str]])
    evidence: dict[int, list[str]] = field(default_factory=dict[int, list[str]])
    gate_commands: list[tuple[str, int]] = field(default_factory=list[tuple[str, int]])
    origins: list[str] = field(default_factory=list[str])
    objections: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])
    pass_id: str = ""
    task_id: str = TASK_ID
    cycle: int = 0


@dataclass
class PanelResult:
    """Итог проверки пакета Панели."""

    verdict: Verdict
    technical_status: str | None
    reasons: list[str]
    proof: dict[str, object]
    ledger_rows: list[LedgerRow]
    details: PanelDetails = field(default_factory=PanelDetails)


@dataclass
class _Issues:
    """Нарушения по классам технических исходов."""

    stale: list[str] = field(default_factory=list[str])
    gate: list[str] = field(default_factory=list[str])
    quorum: list[str] = field(default_factory=list[str])
    consensus: list[str] = field(default_factory=list[str])

    def status(self) -> str | None:
        """Технический исход по приоритету: пакет, гейт, кворум, консенсус."""
        if self.stale:
            return "STALE_PACKAGE"
        if self.gate:
            return "CODE_GATE_RED"
        if self.quorum:
            return "QUORUM_UNAVAILABLE"
        if self.consensus:
            return "CONSENSUS_UNAVAILABLE"
        return None

    def reasons(self) -> list[str]:
        """Все причины в порядке приоритета."""
        return [*self.stale, *self.gate, *self.quorum, *self.consensus]


# --------------------------------------------------------------------------- хеши и JSON


def sha256_bytes(data: bytes) -> str:
    """sha256 байтов в hex."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """sha256 текста в UTF-8."""
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    """sha256 содержимого файла (потоково)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(data: object) -> str:
    """Детерминированный JSON: отсортированные ключи, отступ 2, без экранирования кириллицы."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _as_object(value: object) -> dict[str, object] | None:
    """Приводит JSON-значение к объекту, если это объект."""
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _as_list(value: object) -> list[object] | None:
    """Приводит JSON-значение к списку, если это список."""
    if isinstance(value, list):
        return cast(list[object], value)
    return None


def _is_int(value: object) -> bool:
    """Целое число без булевых значений."""
    return isinstance(value, int) and not isinstance(value, bool)


def _load_json_object(path: Path) -> tuple[dict[str, object] | None, str | None]:
    """Читает JSON-объект; вторым значением возвращает причину отказа."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{path.name}: файл нечитаем ({exc.__class__.__name__})"
    except json.JSONDecodeError as exc:
        return None, f"{path.name}: невалидный JSON ({exc.msg})"
    data = _as_object(raw)
    if data is None:
        return None, f"{path.name}: ожидался JSON-объект"
    return data, None


def _rel(path: Path, root: Path) -> str:
    """Путь относительно корня проекта в POSIX-виде (имя файла, если путь вне корня)."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _abs(path: Path, root: Path) -> Path:
    """Относительный путь отсчитывается от корня проекта."""
    return path if path.is_absolute() else root / path


# --------------------------------------------------------------------------- реестр


def render_ledger_tsv(rows: Sequence[LedgerRow]) -> str:
    """Нормативный TSV реестра: заголовок и по строке на F-ID, перевод строки LF."""
    lines = [LEDGER_HEADER, *("\t".join(row.fields()) for row in rows)]
    return "\n".join(lines) + "\n"


def render_ledger_md(rows: Sequence[LedgerRow], tsv_sha: str) -> str:
    """Проекция реестра для показа: первая строка содержит sha256 TSV."""
    lines = [
        f"sha256 findings-ledger.tsv: {tsv_sha}",
        "",
        "| f_id | severity | judge | location | summary | status | resolution |",
        "|---|---|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(row.fields()) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def parse_ledger_tsv(text: str) -> list[LedgerRow]:
    """Разбирает и проверяет TSV реестра; нарушение формата — `PanelFormatError`."""
    if "\r" in text:
        raise PanelFormatError("реестр: допустим только перевод строки LF")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0] != LEDGER_HEADER:
        raise PanelFormatError("реестр: неверный заголовок")
    rows: list[LedgerRow] = []
    for number, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != LEDGER_COLUMNS:
            raise PanelFormatError(f"реестр, строка {number}: нужно {LEDGER_COLUMNS} колонок")
        row = LedgerRow(*cells)
        if not _F_ID_RE.match(row.f_id):
            raise PanelFormatError(f"реестр, строка {number}: неверный f_id {row.f_id!r}")
        if row.severity not in SEVERITIES:
            raise PanelFormatError(f"реестр, строка {number}: неверная тяжесть {row.severity!r}")
        if row.status not in STATUSES:
            raise PanelFormatError(f"реестр, строка {number}: неверный статус {row.status!r}")
        if row.judge not in SEATS:
            raise PanelFormatError(f"реестр, строка {number}: неверный judge {row.judge!r}")
        if not row.summary or not row.location or not row.resolution:
            raise PanelFormatError(f"реестр, строка {number}: пустое поле")
        rows.append(row)
    ids = [row.f_id for row in rows]
    if len(set(ids)) != len(ids):
        raise PanelFormatError("реестр: повторяющийся f_id")
    return rows


def blocking_counts(rows: Sequence[LedgerRow]) -> tuple[int, int]:
    """Число блокирующих находок: (OPEN, AGREED); блокирующие — BLOCKER и IMPORTANT."""
    open_count = sum(1 for r in rows if r.severity in BLOCKING_SEVERITIES and r.status == "OPEN")
    agreed = sum(1 for r in rows if r.severity in BLOCKING_SEVERITIES and r.status == "AGREED")
    return open_count, agreed


def candidate_for(rows: Sequence[LedgerRow]) -> Literal["ACCEPT", "REJECT"]:
    """Кандидат FREEZE: ACCEPT, если нет блокирующих находок OPEN или AGREED."""
    open_count, agreed = blocking_counts(rows)
    return "ACCEPT" if open_count == 0 and agreed == 0 else "REJECT"


# --------------------------------------------------------------------------- разбор файла судьи


def _split_segments(rest: str) -> tuple[dict[str, str], list[str]]:
    """Делит хвост позиции по ` | ` на ключи `severity=`, `evidence:`, `ARG:`, `NEW:`."""
    values: dict[str, str] = {}
    errors: list[str] = []
    current: str | None = None
    for segment in rest.split(" | "):
        stripped = segment.strip()
        key = next((p for p in _KEY_PREFIXES if stripped.startswith(p)), None)
        if key is not None:
            if key in values:
                errors.append(f"повторный ключ {key}")
            values[key] = stripped[len(key) :].strip()
            current = key
        elif current is not None:
            values[current] = f"{values[current]} | {stripped}"
        else:
            errors.append(f"неизвестный сегмент {stripped!r}")
    return values, errors


def _parse_finding(line: str, doc: JudgeDoc, *, new: bool) -> None:
    """Разбирает `FINDING`/`NEW-FINDING` и добавляет в документ."""
    match = _FINDING_RE.match(line)
    prefix = "NEW-FINDING" if new else "FINDING"
    if match is None or not line.startswith(prefix + " "):
        doc.errors.append(f"неверная строка {prefix}: {line[:80]!r}")
        return
    parts = match.group(3).split(" | ")
    if len(parts) != 2:
        doc.errors.append(f"{prefix} {match.group(1)}: нужно `location | summary` без лишнего |")
        return
    location, summary = parts[0].strip(), parts[1].strip()
    if not _LOCATION_RE.match(location):
        doc.errors.append(f"{prefix} {match.group(1)}: location должен быть file:line")
        return
    if not summary or "|" in summary:
        doc.errors.append(f"{prefix} {match.group(1)}: пустое summary или символ |")
        return
    finding = FindingLine(match.group(1), match.group(2), location, summary)
    target = doc.new_findings if new else doc.findings
    if any(f.local_id == finding.local_id for f in [*doc.findings, *doc.new_findings]):
        doc.errors.append(f"{prefix} {finding.local_id}: повторный local_id в файле")
        return
    target.append(finding)


def _parse_position(line: str, doc: JudgeDoc) -> None:
    """Разбирает строку `POSITION`."""
    match = _POSITION_RE.match(line)
    if match is None:
        doc.errors.append(f"неверная строка POSITION: {line[:80]!r}")
        return
    rest = match.group(3)
    values, errors = _split_segments(rest) if rest else ({}, [])
    doc.errors.extend(f"POSITION {match.group(1)}: {e}" for e in errors)
    severity = values.get("severity=")
    doc.positions.append(
        PositionLine(
            f_id=match.group(1),
            stance=match.group(2),
            severity=severity,
            evidence=values.get("evidence:", ""),
            arg=values.get("ARG:", ""),
            new=values.get("NEW:", ""),
        )
    )


def _parse_c1_line(kind: str, line: str, doc: JudgeDoc) -> None:
    """Разбирает строки тела C1."""
    value = line.split(":", 1)[1].strip()
    if kind == "FREEZE_SHA256":
        if doc.freeze_sha is not None or not _SHA_RE.match(value):
            doc.errors.append("FREEZE_SHA256: повтор или не sha256")
        else:
            doc.freeze_sha = value
    elif kind == "VERDICT":
        if doc.verdict is not None or value not in ("ACCEPT", "REJECT"):
            doc.errors.append("VERDICT: повтор или значение не ACCEPT/REJECT")
        else:
            doc.verdict = value
    elif kind == "OBJECTION":
        match = _OBJECTION_RE.match(line)
        if match is None:
            doc.errors.append("OBJECTION: нужен формат `file:line | дефект`")
        else:
            doc.objections.append((match.group(1), match.group(2).strip()))
    elif kind == "FALLBACK_CONSENT":
        if value == "YES":
            doc.fallback = True
        else:
            doc.errors.append("FALLBACK_CONSENT: допустимо только YES")


def _parse_r1_line(kind: str, line: str, doc: JudgeDoc) -> None:
    """Разбирает строки тела R1."""
    if kind == "COVERAGE":
        match = _COVERAGE_RE.match(line)
        if match is None or doc.coverage:
            doc.errors.append("COVERAGE: нужны ровно пять ключей 1..5 со значением OK или ISSUE")
        else:
            doc.coverage = {n: match.group(n) for n in CRITERIA}
    elif kind == "FINDINGS":
        if line.strip() == "FINDINGS: none":
            doc.no_findings = True
        else:
            doc.errors.append("FINDINGS: допустимо только `FINDINGS: none`")
    elif kind == "FINDING":
        _parse_finding(line, doc, new=False)
    elif kind == "EVIDENCE":
        match = _EVIDENCE_RE.match(line)
        if match is None:
            doc.errors.append("EVIDENCE: нужен формат `EVIDENCE <1..5>: текст`")
        else:
            doc.evidence.setdefault(int(match.group(1)), []).append(match.group(2).strip())


def _parse_header(lines: list[str], doc: JudgeDoc) -> int:
    """Читает пять строк заголовка; возвращает индекс первой строки тела (или -1)."""
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    values: dict[str, str] = {}
    for key in ("SEAT", "ROUND", "HAT", "PROCEDURE_ACCEPTED", "ORIGIN"):
        match = _HEADER_RE.match(lines[index].strip()) if index < len(lines) else None
        if match is None or match.group(1) != key:
            doc.errors.append(f"заголовок: ожидалась строка `{key}: значение`")
            return -1
        values[key] = match.group(2).strip()
        index += 1
    doc.seat, doc.round, doc.hat = values["SEAT"], values["ROUND"], values["HAT"]
    doc.procedure, doc.origin = values["PROCEDURE_ACCEPTED"], values["ORIGIN"]
    return index


def _check_shape(doc: JudgeDoc, round_name: str, headings: list[str]) -> None:
    """Проверяет обязательные элементы тела по типу раунда."""
    if round_name == "R1":
        if not doc.coverage:
            doc.errors.append("R1: нет строки COVERAGE")
        if doc.no_findings == bool(doc.findings):
            doc.errors.append("R1: нужен либо `FINDINGS: none`, либо хотя бы один FINDING")
    elif round_name in DEBATE_ROUNDS:
        if ANSWERS_HEADING not in headings or QUESTIONS_HEADING not in headings:
            doc.errors.append("D: обе секции (ответы и вопросы) обязательны")
        elif headings.index(ANSWERS_HEADING) > headings.index(QUESTIONS_HEADING):
            doc.errors.append("D: секция ответов должна идти раньше секции вопросов")
        if round_name == "D3":
            for question in doc.questions:
                if question.lstrip("-* ").rstrip(". ").casefold() != NO_QUESTIONS:
                    doc.errors.append("D3: в секции вопросов допустимо только «вопросов нет»")
                    break
    elif round_name == "C1":
        if doc.freeze_sha is None:
            doc.errors.append("C1: нет FREEZE_SHA256")
        if doc.verdict is None:
            doc.errors.append("C1: нет VERDICT")
        if not doc.fallback:
            doc.errors.append("C1: нет `FALLBACK_CONSENT: YES`")


def parse_judge_text(text: str, round_name: str) -> JudgeDoc:
    """Разбирает файл судьи для раунда `round_name`; нарушения формата — в `doc.errors`."""
    doc = JudgeDoc()
    lines = [ln.rstrip("\r") for ln in text.lstrip("\ufeff").split("\n")]
    start = _parse_header(lines, doc)
    if start < 0:
        return doc
    group = "D" if round_name in DEBATE_ROUNDS else round_name
    allowed = _ALLOWED_KINDS.get(group, frozenset())
    section = ""
    headings: list[str] = []
    for raw in lines[start:]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            section = line
            headings.append(line)
            doc.has_answers = doc.has_answers or line == ANSWERS_HEADING
            doc.has_questions = doc.has_questions or line == QUESTIONS_HEADING
            continue
        kind_match = _KIND_RE.match(line)
        if kind_match is None:
            if section == QUESTIONS_HEADING:
                doc.questions.append(line)
            continue
        kind = kind_match.group(1)
        if kind not in allowed:
            doc.errors.append(f"{round_name}: строка {kind} недопустима в этом раунде")
        elif kind == "POSITION":
            _parse_position(line, doc)
        elif kind == "NEW-FINDING":
            _parse_finding(line, doc, new=True)
        elif group == "C1":
            _parse_c1_line(kind, line, doc)
        else:
            _parse_r1_line(kind, line, doc)
    _check_shape(doc, round_name, headings)
    return doc


def load_judge(path: Path, round_name: str) -> JudgeDoc:
    """Читает и разбирает файл судьи; нечитаемый файл даёт документ с ошибкой."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        doc = JudgeDoc()
        doc.errors.append(f"файл нечитаем ({exc.__class__.__name__})")
        return doc
    return parse_judge_text(text, round_name)


# --------------------------------------------------------------------------- проигрыш раундов


@dataclass
class _State:
    """Изменяемое состояние находки при проигрыше раундов."""

    f_id: str
    severity: str
    judge: str
    location: str
    summary: str
    status: str
    resolution: str
    proposed_severity: str | None = None

    def row(self) -> LedgerRow:
        """Неизменяемая строка реестра."""
        return LedgerRow(
            self.f_id,
            self.severity,
            self.judge,
            self.location,
            self.summary,
            self.status,
            self.resolution,
        )


def _origin_resolution(round_name: str) -> str:
    """Текст resolution у новой находки."""
    return f"{round_name}:unresolved" if round_name == "D3" else f"{round_name}:open"


def _new_states(
    docs: dict[str, JudgeDoc], round_name: str, states: list[_State], *, new: bool
) -> None:
    """Присваивает F-ID находкам раунда по порядку judge-1..3 и сверху вниз."""
    for seat in SEATS:
        doc = docs[seat]
        for item in doc.new_findings if new else doc.findings:
            states.append(
                _State(
                    f_id=f"F-{len(states) + 1:03d}",
                    severity=item.severity,
                    judge=seat,
                    location=item.location,
                    summary=item.summary,
                    status="OPEN",
                    resolution=_origin_resolution(round_name),
                )
            )


def _check_position(
    pos: PositionLine,
    seat: str,
    state: _State,
    last: dict[tuple[str, str], str],
    round_name: str,
) -> list[str]:
    """Правила позиции судьи по открытой находке; возвращает список нарушений."""
    errors: list[str] = []
    tag = f"{round_name}/{seat}/{pos.f_id}"
    if not (pos.evidence or pos.arg or pos.new):
        errors.append(f"{tag}: нет непустого evidence:/ARG:/NEW:")
    if pos.stance == "AMEND":
        if state.judge != seat:
            errors.append(f"{tag}: AMEND допустим только автору находки")
        if pos.severity not in SEVERITIES:
            errors.append(f"{tag}: AMEND требует severity=BLOCKER|IMPORTANT|MINOR")
        elif pos.severity == state.severity:
            errors.append(f"{tag}: AMEND не меняет тяжесть {state.severity}")
    elif pos.severity is not None:
        errors.append(f"{tag}: severity= допустим только в AMEND")
    previous = last.get((seat, pos.f_id), "AGREE" if state.judge == seat else None)
    if previous is not None and previous != pos.stance and not (pos.arg or pos.new):
        errors.append(f"{tag}: смена позиции {previous}->{pos.stance} без ARG:/NEW:")
    last[(seat, pos.f_id)] = pos.stance
    return errors


def _apply_round(
    docs: dict[str, JudgeDoc],
    round_name: str,
    states: list[_State],
    last: dict[tuple[str, str], str],
) -> list[str]:
    """Один раунд D: проверка позиций и пересчёт статусов; затем NEW-FINDING."""
    errors: list[str] = []
    by_id = {s.f_id: s for s in states}
    open_ids = [s.f_id for s in states if s.status == "OPEN"]
    taken: dict[str, dict[str, PositionLine]] = {}
    for seat in SEATS:
        seen: dict[str, PositionLine] = {}
        for pos in docs[seat].positions:
            if pos.f_id not in by_id:
                errors.append(f"{round_name}/{seat}: позиция по неизвестной {pos.f_id}")
            elif pos.f_id in seen:
                errors.append(f"{round_name}/{seat}: две позиции по {pos.f_id}")
            else:
                seen[pos.f_id] = pos
        for f_id in open_ids:
            if f_id not in seen:
                errors.append(f"{round_name}/{seat}: нет позиции по открытой {f_id}")
            else:
                errors.extend(_check_position(seen[f_id], seat, by_id[f_id], last, round_name))
        taken[seat] = seen
    for f_id in open_ids:
        state = by_id[f_id]
        votes = {seat: taken[seat].get(f_id) for seat in SEATS}
        if any(v is None for v in votes.values()):
            continue
        stances = {seat: v.stance for seat, v in votes.items() if v is not None}
        author = votes[state.judge]
        amended = author.severity if author is not None and author.stance == "AMEND" else None
        if amended is not None and amended in SEVERITIES:
            if SEVERITIES.index(amended) < SEVERITIES.index(state.severity):
                state.severity = amended
                state.proposed_severity = None
                state.resolution = f"{round_name}:amended-{state.severity}"
                continue
            state.proposed_severity = amended
        others_agree = all(stances[seat] == "AGREE" for seat in SEATS if seat != state.judge)
        if others_agree and stances[state.judge] in ("AGREE", "AMEND"):
            if state.proposed_severity is not None:
                state.severity = state.proposed_severity
                state.proposed_severity = None
            state.status = "AGREED"
            state.resolution = f"{round_name}:agree-3/3"
        elif stances[state.judge] == "WITHDRAW" and "AGREE" not in stances.values():
            state.status = "WITHDRAWN"
            state.resolution = f"{round_name}:withdrawn-by-author"
        elif state.proposed_severity is not None:
            state.resolution = f"{round_name}:amend-pending-{state.proposed_severity}"
        else:
            state.resolution = f"{round_name}:unresolved"
    _new_states(docs, round_name, states, new=True)
    return errors


def replay(
    docs: dict[str, dict[str, JudgeDoc]], rounds: Sequence[str]
) -> tuple[list[LedgerRow], list[str]]:
    """Проигрывает R1 и перечисленные раунды D; возвращает реестр и нарушения."""
    states: list[_State] = []
    last: dict[tuple[str, str], str] = {}
    _new_states(docs["R1"], "R1", states, new=False)
    errors: list[str] = []
    for round_name in rounds:
        errors.extend(_apply_round(docs[round_name], round_name, states, last))
    return [s.row() for s in states], errors


def _round_dir(panel_dir: Path, round_name: str) -> Path:
    """Каталог раунда: `r1`, `d1`, …"""
    return panel_dir / round_name.lower()


def _load_rounds(panel_dir: Path) -> tuple[dict[str, dict[str, JudgeDoc]], list[str], list[str]]:
    """Загружает R1 и доступные D; возвращает документы, список раундов D и нарушения."""
    docs: dict[str, dict[str, JudgeDoc]] = {}
    errors: list[str] = []
    present: list[str] = []
    for round_name in ("R1", *DEBATE_ROUNDS):
        files = {seat: _round_dir(panel_dir, round_name) / f"{seat}.md" for seat in SEATS}
        existing = [seat for seat in SEATS if files[seat].is_file()]
        if not existing and round_name != "R1":
            break
        round_docs: dict[str, JudgeDoc] = {}
        for seat in SEATS:
            if seat not in existing:
                errors.append(f"{round_name}/{seat}: нет файла судьи")
                round_docs[seat] = JudgeDoc()
                continue
            doc = load_judge(files[seat], round_name)
            errors.extend(f"{round_name}/{seat}: {e}" for e in doc.errors)
            round_docs[seat] = doc
        docs[round_name] = round_docs
        if round_name != "R1":
            present.append(round_name)
    return docs, present, errors


def build_ledger(panel_dir: Path) -> list[LedgerRow]:
    """Пересобирает реестр из файлов раундов `panel_dir`; нарушения — `PanelFormatError`.

    Берёт R1 и все подряд существующие D1..D3 (промежуточный реестр после R1 или D допустим).
    """
    docs, present, errors = _load_rounds(panel_dir)
    if not errors:
        rows, replay_errors = replay(docs, present)
        if not replay_errors:
            return rows
        errors = replay_errors
    raise PanelFormatError("; ".join(errors))


# --------------------------------------------------------------------------- паспорт и freeze


def _input_paths(team_dir: Path, root: Path) -> dict[str, Path]:
    """Пять входов прохода: спека, риск-план, рубрика, handoff Кодера, свидетельство CODE_GATE."""
    return {
        "spec": root / SPEC_PATH,
        "risk_plan": root / RISK_PLAN_PATH,
        "rubric": root / RUBRIC_PATH,
        "coder_handoff": team_dir / "handoff-coder.md",
        "code_gate": team_dir / "code-gate.json",
    }


def compute_code_tree_sha256(root: Path) -> str:
    """sha256 продуктового кода: `app/`, `tests/`, `alembic/`, `pyproject.toml` (без кэшей)."""
    files: list[Path] = []
    for name in CODE_TREE_PATHS:
        base = root / name
        if base.is_file():
            files.append(base)
        elif base.is_dir():
            files.extend(
                path
                for path in base.rglob("*")
                if path.is_file()
                and path.suffix != ".pyc"
                and not CODE_TREE_SKIP_NAMES.intersection(path.relative_to(root).parts)
            )
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(f"{path.relative_to(root).as_posix()}\0{sha256_file(path)}\n".encode())
    return digest.hexdigest()


def input_hashes(team_dir: Path, root: Path) -> dict[str, str]:
    """sha256 пяти входов и дерева кода; отсутствие файла входа — `PanelFormatError`."""
    result: dict[str, str] = {}
    for key, path in _input_paths(team_dir, root).items():
        if not path.is_file():
            raise PanelFormatError(f"нет входного файла {key}: {_rel(path, root)}")
        result[key] = sha256_file(path)
    result[CODE_TREE_KEY] = compute_code_tree_sha256(root)
    return result


def default_pass_id(hashes: dict[str, str], cycle: int) -> str:
    """Детерминированный pass_id из хешей входов и номера цикла."""
    digest = sha256_text("|".join(f"{k}={hashes[k]}" for k in sorted(hashes)) + f"|{cycle}")
    return f"{TASK_ID}-c{cycle}-{digest[:8]}"


def write_manifest(
    team_dir: Path,
    root: Path,
    model: str = DEFAULT_MODEL,
    cycle: int = 1,
    pass_id: str | None = None,
) -> str:
    """Пишет `panel/manifest.json` и возвращает его sha256."""
    team = _abs(team_dir, root)
    hashes = input_hashes(team, root)
    manifest: dict[str, object] = {
        "protocol": PROTOCOL,
        "pass_id": pass_id or default_pass_id(hashes, cycle),
        "task_id": TASK_ID,
        "cycle": cycle,
        "model": model,
        "seats": list(SEATS),
        "inputs_sha256": hashes,
        "calls_budget": CALLS_BUDGET,
    }
    path = team / "panel" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(manifest), encoding="utf-8")
    return sha256_file(path)


def write_ledger(team_dir: Path, root: Path = ROOT) -> str:
    """Пересобирает `findings-ledger.tsv` и `.md`; возвращает sha256 TSV."""
    panel = _abs(team_dir, root) / "panel"
    rows = build_ledger(panel)
    tsv = render_ledger_tsv(rows)
    tsv_sha = sha256_text(tsv)
    (panel / "findings-ledger.tsv").write_text(tsv, encoding="utf-8")
    (panel / "findings-ledger.md").write_text(render_ledger_md(rows, tsv_sha), encoding="utf-8")
    return tsv_sha


def freeze_payload(
    pass_id: str, manifest_sha: str, rows: Sequence[LedgerRow], code_tree: str
) -> dict[str, object]:
    """Содержимое `freeze.json` по реестру и дереву кода."""
    open_count, agreed = blocking_counts(rows)
    return {
        CODE_TREE_KEY: code_tree,
        "protocol": PROTOCOL,
        "pass_id": pass_id,
        "manifest_sha256": manifest_sha,
        "ledger_sha256": sha256_text(render_ledger_tsv(rows)),
        "candidate": candidate_for(rows),
        "open_blocking": open_count,
        "agreed_blocking": agreed,
    }


def _manifest_pass_id(manifest: Path) -> str:
    """pass_id из паспорта; битый паспорт — `PanelFormatError`."""
    data, error = _load_json_object(manifest)
    pass_id = data.get("pass_id") if data is not None else None
    if not isinstance(pass_id, str) or not pass_id:
        raise PanelFormatError(error or "manifest.json: нет pass_id")
    return pass_id


def _manifest_code_tree(manifest: Path) -> str | None:
    """`code_tree_sha256` из паспорта прохода (None, если не записан)."""
    data, _ = _load_json_object(manifest)
    bound = _as_object(data.get("inputs_sha256")) if data is not None else None
    value = bound.get(CODE_TREE_KEY) if bound is not None else None
    return value if isinstance(value, str) else None


def write_freeze(team_dir: Path, root: Path = ROOT) -> str:
    """Пишет `panel/freeze.json` (кандидат FREEZE); возвращает его sha256 (digest для C1)."""
    panel = _abs(team_dir, root) / "panel"
    manifest = panel / "manifest.json"
    if not manifest.is_file():
        raise PanelFormatError("нет panel/manifest.json")
    code_tree = compute_code_tree_sha256(root)
    if _manifest_code_tree(manifest) != code_tree:
        raise PanelFormatError(STALE_CODE_TREE)
    rows = build_ledger(panel)
    tsv_path = panel / "findings-ledger.tsv"
    if not tsv_path.is_file() or tsv_path.read_text(encoding="utf-8") != render_ledger_tsv(rows):
        raise PanelFormatError("реестр не актуален: сначала выполните подкоманду ledger")
    payload = freeze_payload(_manifest_pass_id(manifest), sha256_file(manifest), rows, code_tree)
    path = panel / "freeze.json"
    path.write_text(canonical_json(payload), encoding="utf-8")
    return sha256_file(path)


# --------------------------------------------------------------------------- проверка пакета


def _check_manifest_shape(data: dict[str, object]) -> list[str]:
    """Структура паспорта прохода."""
    errors: list[str] = []
    if data.get("protocol") != PROTOCOL:
        errors.append(f"manifest.json: protocol должен быть {PROTOCOL}")
    for key in ("pass_id", "task_id", "model"):
        value = data.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"manifest.json: нет строки {key}")
    if not _is_int(data.get("cycle")):
        errors.append("manifest.json: cycle должен быть целым")
    if data.get("seats") != list(SEATS):
        errors.append("manifest.json: seats должен быть judge-1, judge-2, judge-3")
    if data.get("calls_budget") != CALLS_BUDGET:
        errors.append(f"manifest.json: calls_budget должен быть {CALLS_BUDGET}")
    hashes = _as_object(data.get("inputs_sha256"))
    if hashes is None or set(hashes) != {*INPUT_KEYS, CODE_TREE_KEY}:
        errors.append(
            "manifest.json: inputs_sha256 должен содержать пять входов и code_tree_sha256"
        )
    return errors


def _check_code_gate(
    path: Path, current: dict[str, str], issues: _Issues, details: PanelDetails
) -> None:
    """Свидетельство CODE_GATE: команды, коды выхода, привязка входов."""
    data, error = _load_json_object(path)
    if data is None:
        issues.gate.append(error or "code-gate.json нечитаем")
        return
    if data.get("task_id") != TASK_ID:
        issues.stale.append(f"code-gate.json: task_id должен быть {TASK_ID}")
    if data.get("source") not in ORIGINS:
        issues.gate.append("code-gate.json: source должен быть reference-fixture или live")
    commands: list[tuple[str, int]] = []
    for item in _as_list(data.get("commands")) or []:
        entry = _as_object(item)
        cmd = entry.get("cmd") if entry is not None else None
        code = entry.get("exit_code") if entry is not None else None
        if not isinstance(cmd, str) or not isinstance(code, int) or isinstance(code, bool):
            issues.gate.append("code-gate.json: команда без cmd/exit_code")
            continue
        commands.append((cmd, code))
    details.gate_commands = commands
    for required in REQUIRED_COMMANDS:
        found = [code for cmd, code in commands if required in cmd]
        if not found:
            issues.gate.append(f"CODE_GATE: нет команды `{required}`")
        elif any(code != 0 for code in found):
            issues.gate.append(f"CODE_GATE красный: `{required}` вернула не 0")
    bound = _as_object(data.get("inputs_sha256"))
    for key in ("spec", "risk_plan", "coder_handoff"):
        if bound is None or bound.get(key) != current.get(key):
            issues.stale.append(f"code-gate.json устарел: sha256 входа {key} не совпал")


def _check_header(doc: JudgeDoc, seat: str, round_name: str, manifest_sha: str) -> list[str]:
    """Заголовок файла судьи: seat, раунд, ротация шляп, принятая процедура, происхождение."""
    errors: list[str] = []
    if doc.seat != seat:
        errors.append(f"SEAT {doc.seat!r} не совпадает с файлом (дубликат seat)")
    if doc.round != round_name:
        errors.append(f"ROUND {doc.round!r} не совпадает с каталогом раунда")
    if doc.hat != ROTATION[round_name][seat]:
        errors.append(f"HAT {doc.hat!r}: по ротации ожидалась {ROTATION[round_name][seat]!r}")
    if doc.procedure != manifest_sha:
        errors.append("PROCEDURE_ACCEPTED не совпал с sha256 manifest.json")
    if doc.origin not in ORIGINS:
        errors.append("ORIGIN должен быть reference-fixture или live")
    return errors


def _collect_docs(
    panel: Path, manifest_sha: str, issues: _Issues, rounds_hash: dict[str, dict[str, str]]
) -> dict[str, dict[str, JudgeDoc]]:
    """Читает 15 файлов судей; нарушения раскладывает по классам исходов."""
    docs: dict[str, dict[str, JudgeDoc]] = {}
    for round_name in ROUNDS:
        directory = _round_dir(panel, round_name)
        expected = {f"{seat}.md" for seat in SEATS}
        if directory.is_dir():
            for entry in sorted(directory.iterdir()):
                if entry.name not in expected and not entry.name.startswith("."):
                    issues.consensus.append(
                        f"{round_name}: лишний файл {entry.name} (дубликат seat или чужой файл)"
                    )
        docs[round_name] = {}
        rounds_hash[round_name] = {}
        for seat in SEATS:
            path = directory / f"{seat}.md"
            if not path.is_file():
                issues.quorum.append(f"{round_name}/{seat}: нет файла судьи")
                continue
            doc = load_judge(path, round_name)
            docs[round_name][seat] = doc
            rounds_hash[round_name][seat] = sha256_file(path)
            if not doc.errors:
                found = _check_header(doc, seat, round_name, manifest_sha)
                doc.errors.extend(found)
            issues.consensus.extend(f"{round_name}/{seat}: {e}" for e in doc.errors)
    return docs


def _complete(docs: dict[str, dict[str, JudgeDoc]], names: Sequence[str]) -> bool:
    """Все файлы перечисленных раундов присутствуют и разобраны без нарушений."""
    return all(
        len(docs[n]) == len(SEATS) and all(not d.errors for d in docs[n].values()) for n in names
    )


def _check_ledger_files(panel: Path, rows: Sequence[LedgerRow], issues: _Issues) -> None:
    """Файлы реестра обязаны совпадать с пересчётом по файлам раундов."""
    tsv = render_ledger_tsv(rows)
    expected = {
        "findings-ledger.tsv": tsv,
        "findings-ledger.md": render_ledger_md(rows, sha256_text(tsv)),
    }
    for name, content in expected.items():
        path = panel / name
        if not path.is_file():
            issues.consensus.append(f"нет {name}: выполните подкоманду ledger")
            continue
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            actual = ""
        if actual != content:
            issues.consensus.append(f"{name} расходится с файлами раундов")


def _evaluate_c1(
    docs: dict[str, JudgeDoc],
    digest: str | None,
    candidate: str,
    issues: _Issues,
    details: PanelDetails,
) -> Literal["ACCEPT", "REJECT"] | None:
    """Исход C1 по §3.7; None — технический исход."""
    before = len(issues.consensus)
    votes: list[str] = []
    for seat in SEATS:
        doc = docs[seat]
        if doc.errors:
            continue
        if digest is not None and doc.freeze_sha != digest:
            issues.consensus.append(f"C1/{seat}: FREEZE_SHA256 не совпал с digest freeze.json")
        if doc.verdict == "REJECT" and candidate == "ACCEPT" and not doc.objections:
            issues.consensus.append(f"C1/{seat}: REJECT при кандидате ACCEPT без OBJECTION")
        votes.append(doc.verdict or "")
        details.objections.extend((seat, loc, defect) for loc, defect in doc.objections)
    if len(issues.consensus) != before or issues.status() is not None:
        return None
    if candidate == "ACCEPT":
        return "ACCEPT" if all(v == "ACCEPT" for v in votes) else "REJECT"
    if all(v == "REJECT" for v in votes):
        return "REJECT"
    issues.consensus.append("C1: ACCEPT противоречит кандидату REJECT")
    return None


def _fill_details(docs: dict[str, dict[str, JudgeDoc]], details: PanelDetails) -> None:
    """Собирает COVERAGE, EVIDENCE и происхождение для отчёта."""
    for number in CRITERIA:
        details.coverage[number] = {
            seat: doc.coverage[number]
            for seat, doc in docs.get("R1", {}).items()
            if number in doc.coverage
        }
        merged: list[str] = []
        for doc in docs.get("R1", {}).values():
            merged.extend(t for t in doc.evidence.get(number, []) if t not in merged)
        details.evidence[number] = merged
    origins = {d.origin for per_round in docs.values() for d in per_round.values() if d.origin}
    details.origins = sorted(origins)


def _blocking_reasons(rows: Sequence[LedgerRow], details: PanelDetails) -> list[str]:
    """Причины согласованного REJECT: блокирующие находки и возражения C1."""
    reasons = [
        f"{r.f_id} {r.severity} {r.status}: {r.location} | {r.summary}"
        for r in rows
        if r.severity in BLOCKING_SEVERITIES and r.status in ("OPEN", "AGREED")
    ]
    reasons.extend(f"C1 {seat}: {loc} | {defect}" for seat, loc, defect in details.objections)
    return reasons


def _empty_proof() -> dict[str, object]:
    """Каркас consensus-proof.json со всеми обязательными ключами."""
    return {
        "protocol": PROTOCOL,
        "task_id": TASK_ID,
        "cycle": None,
        "pass_id": None,
        "manifest_sha256": None,
        "ledger_sha256": None,
        "freeze_sha256": None,
        "candidate": None,
        "code_tree_sha256": None,
        "rounds": {name: {} for name in ROUNDS},
        "calls": 0,
        "verdict": None,
        "technical_status": None,
        "open_blocking": None,
        "agreed_blocking": None,
        "reasons": [],
    }


def _escalate(issues: _Issues, proof: dict[str, object], details: PanelDetails) -> PanelResult:
    """Технический исход: verdict=null."""
    reasons = issues.reasons()
    proof["technical_status"] = issues.status()
    proof["reasons"] = reasons
    return PanelResult("ESCALATE", issues.status(), reasons, proof, [], details)


def _load_manifest(
    panel: Path, issues: _Issues, details: PanelDetails
) -> tuple[dict[str, object], str] | None:
    """Паспорт прохода и его sha256; None — пакет нельзя проверять дальше."""
    path = panel / "manifest.json"
    if not path.is_file():
        issues.stale.append("нет panel/manifest.json: проход не инициализирован")
        return None
    data, error = _load_json_object(path)
    if data is None:
        issues.consensus.append(error or "manifest.json нечитаем")
        return None
    problems = _check_manifest_shape(data)
    issues.consensus.extend(problems)
    if problems:
        return None
    details.pass_id = str(data["pass_id"])
    cycle = data["cycle"]
    details.cycle = cycle if isinstance(cycle, int) else 0
    return data, sha256_file(path)


def _check_inputs(
    team: Path, root: Path, manifest: dict[str, object], issues: _Issues
) -> dict[str, str]:
    """Привязка входов к паспорту: любое расхождение — устаревший пакет."""
    current: dict[str, str] = {}
    for key, path in _input_paths(team, root).items():
        if path.is_file():
            current[key] = sha256_file(path)
        else:
            issues.stale.append(f"нет входного файла {key}: {_rel(path, root)}")
    current[CODE_TREE_KEY] = compute_code_tree_sha256(root)
    bound = _as_object(manifest.get("inputs_sha256")) or {}
    for key, value in current.items():
        if key == CODE_TREE_KEY and bound.get(key) != value:
            issues.stale.append(STALE_CODE_TREE)
        elif bound.get(key) != value:
            issues.stale.append(f"пакет устарел: sha256 входа {key} не совпал с manifest.json")
    return current


def check_panel(team_dir: Path, root: Path) -> PanelResult:
    """Проверяет весь пакет Панели и возвращает исход; файлов не пишет.

    Args:
        team_dir: каталог `.ai-team` (абсолютный или относительно `root`).
        root: корень проекта (относительно него лежат спека, риск-план и рубрика).

    Returns:
        PanelResult: READY (единогласный ACCEPT), REJECT (согласованный REJECT) или ESCALATE
        с одним из технических исходов (STALE_PACKAGE, CODE_GATE_RED, QUORUM_UNAVAILABLE,
        CONSENSUS_UNAVAILABLE).
    """
    team = _abs(team_dir, root)
    panel = team / "panel"
    issues = _Issues()
    details = PanelDetails()
    proof = _empty_proof()
    loaded = _load_manifest(panel, issues, details)
    if loaded is None:
        return _escalate(issues, proof, details)
    manifest, manifest_sha = loaded
    current = _check_inputs(team, root, manifest, issues)
    proof[CODE_TREE_KEY] = current[CODE_TREE_KEY]
    if (team / "code-gate.json").is_file():
        _check_code_gate(team / "code-gate.json", current, issues, details)
    if issues.status() in ("STALE_PACKAGE", "CODE_GATE_RED"):
        return _escalate(issues, proof, details)
    proof.update(
        cycle=details.cycle, pass_id=details.pass_id, manifest_sha256=manifest_sha, task_id=TASK_ID
    )
    rounds_hash = cast(dict[str, dict[str, str]], proof["rounds"])
    docs = _collect_docs(panel, manifest_sha, issues, rounds_hash)
    proof["calls"] = sum(len(v) for v in rounds_hash.values())
    _fill_details(docs, details)
    rows: list[LedgerRow] = []
    outcome: Literal["ACCEPT", "REJECT"] | None = None
    if _complete(docs, ("R1", *DEBATE_ROUNDS)):
        rows, replay_errors = replay(docs, DEBATE_ROUNDS)
        issues.consensus.extend(replay_errors)
        _check_ledger_files(panel, rows, issues)
        open_count, agreed = blocking_counts(rows)
        candidate = candidate_for(rows)
        tsv_sha = sha256_text(render_ledger_tsv(rows))
        proof.update(
            candidate=candidate,
            ledger_sha256=tsv_sha,
            open_blocking=open_count,
            agreed_blocking=agreed,
        )
        freeze = panel / "freeze.json"
        digest: str | None = None
        if not freeze.is_file():
            issues.consensus.append("нет freeze.json: выполните подкоманду freeze")
        else:
            digest = sha256_file(freeze)
            proof["freeze_sha256"] = digest
            payload = freeze_payload(details.pass_id, manifest_sha, rows, current[CODE_TREE_KEY])
            if freeze.read_text(encoding="utf-8") != canonical_json(payload):
                issues.consensus.append("freeze.json расходится с пересчётом по реестру")
        if _complete(docs, ("C1",)):
            outcome = _evaluate_c1(docs["C1"], digest, candidate, issues, details)
    status = issues.status()
    proof["technical_status"] = status
    if status is not None or outcome is None:
        proof["reasons"] = issues.reasons()
        return PanelResult("ESCALATE", status, issues.reasons(), proof, rows, details)
    reasons = _blocking_reasons(rows, details) if outcome == "REJECT" else []
    proof["verdict"] = outcome
    proof["reasons"] = reasons
    return PanelResult(
        "READY" if outcome == "ACCEPT" else "REJECT", None, reasons, proof, rows, details
    )


# --------------------------------------------------------------------------- вывод итогов


def render_verdict_md(result: PanelResult, proof_sha: str, team_rel: str) -> str:
    """Детерминированный `verdict.md` без временных меток."""
    head = {"READY": "READY", "REJECT": "REWORK", "ESCALATE": "ESCALATE"}[result.verdict]
    tail = {"READY": "VERDICT: ACCEPT", "REJECT": "VERDICT: REJECT", "ESCALATE": "verdict: null"}
    proof = result.proof
    details = result.details
    origins = ", ".join(details.origins) or "нет данных"
    lines = [
        f"Вердикт: {head}",
        "",
        tail[result.verdict],
        f"Run: pass_id={proof.get('pass_id') or 'нет данных'}",
        f"Cycle: {proof.get('cycle') if proof.get('cycle') is not None else 'нет данных'}",
        f"Origin: {origins}",
        f"Artifact-SHA256: {proof.get('ledger_sha256') or 'нет данных'}",
        f"Consensus-Proof: {team_rel}/consensus-proof.json (sha256 {proof_sha})",
        "",
        "## Обоснование по 5 критериям",
        "",
    ]
    gate = "; ".join(f"{cmd}={code}" for cmd, code in details.gate_commands) or "нет данных"
    for number in CRITERIA:
        marks = details.coverage.get(number, {})
        coverage = ", ".join(f"{seat}={mark}" for seat, mark in marks.items()) or "нет данных"
        parts = [f"{number}. {CRITERIA_NAMES[number]}: COVERAGE R1: {coverage}."]
        if number == 3:
            parts.append(f"CODE_GATE: {gate}.")
        facts = details.evidence.get(number, [])
        if facts:
            parts.append("Факт: " + "; ".join(facts) + ".")
        lines.append(" ".join(parts))
    lines.extend(["", "Замечания ISSUE из R1 разобраны в дебатах: итоговый статус — ниже.", ""])
    lines.append("## Находки")
    lines.append("")
    if not result.ledger_rows:
        lines.append("Находок нет.")
    lines.extend(
        f"- {r.f_id} [{r.severity}] {r.status} ({r.resolution}) {r.judge} {r.location}: {r.summary}"
        for r in result.ledger_rows
    )
    if details.objections:
        lines.extend(["", "## Возражения C1", ""])
        lines.extend(f"- {seat}: {loc} | {defect}" for seat, loc, defect in details.objections)
    if result.verdict != "READY" and result.reasons:
        lines.extend(["", "## Причины", ""])
        lines.extend(f"- {reason}" for reason in result.reasons)
    return "\n".join(lines) + "\n"


def write_artifacts(result: PanelResult, team_dir: Path, root: Path = ROOT) -> str:
    """Пишет `consensus-proof.json` и `verdict.md`; возвращает sha256 consensus-proof."""
    team = _abs(team_dir, root)
    team.mkdir(parents=True, exist_ok=True)
    proof_path = team / "consensus-proof.json"
    proof_path.write_text(canonical_json(result.proof), encoding="utf-8")
    proof_sha = sha256_file(proof_path)
    verdict = render_verdict_md(result, proof_sha, _rel(team, root))
    (team / "verdict.md").write_text(verdict, encoding="utf-8")
    return proof_sha


def run_live_checks(root: Path) -> dict[str, int]:
    """Настоящие `ruff check` и `pytest -q`: коды выхода для proof (флаг --run-checks)."""
    commands = {
        "ruff_check": [sys.executable, "-m", "ruff", "check", "."],
        "pytest": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
    }
    codes: dict[str, int] = {}
    for name, cmd in commands.items():
        try:
            done = subprocess.run(
                cmd,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=LIVE_CHECK_TIMEOUT_SECONDS,
            )
            codes[name] = done.returncode
        except subprocess.TimeoutExpired:
            codes[name] = 124
    return codes


def _apply_live_checks(result: PanelResult, codes: dict[str, int]) -> PanelResult:
    """Красная живая проверка превращает исход в CODE_GATE_RED."""
    red = [f"живая проверка {name} вернула {code}" for name, code in codes.items() if code != 0]
    if not red:
        return result
    proof = dict(result.proof)
    proof.update(verdict=None, technical_status="CODE_GATE_RED", reasons=[*red])
    return replace(
        result, verdict="ESCALATE", technical_status="CODE_GATE_RED", reasons=red, proof=proof
    )


def _gate_codes(team: Path) -> dict[str, int]:
    """Коды выхода из свидетельства CODE_GATE (для proof без --run-checks)."""
    data, _ = _load_json_object(team / "code-gate.json")
    codes: dict[str, int] = {}
    for item in _as_list(data.get("commands") if data else None) or []:
        entry = _as_object(item)
        cmd = entry.get("cmd") if entry else None
        code = entry.get("exit_code") if entry else None
        if isinstance(cmd, str) and isinstance(code, int):
            codes[cmd] = code
    return codes


def run_verify(
    team_dir: Path, out_path: Path, root: Path = ROOT, *, run_checks: bool = False
) -> int:
    """Режим по умолчанию: проверка пакета, запись итогов, печать `GATE`/`VERDICT`."""
    team = _abs(team_dir, root)
    out = _abs(out_path, root)
    result = check_panel(team, root)
    codes = run_live_checks(root) if run_checks else _gate_codes(team)
    if run_checks:
        result = _apply_live_checks(result, codes)
    proof_sha = write_artifacts(result, team, root)
    gate_proof: dict[str, object] = {
        "task_id": TASK_ID,
        "verdict": result.proof.get("verdict"),
        "consensus_proof_sha256": proof_sha,
        "checks_exit_codes": codes,
        CODE_TREE_KEY: result.proof.get(CODE_TREE_KEY),
        "ledger_sha256": result.proof.get("ledger_sha256"),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(canonical_json(gate_proof), encoding="utf-8")
    if result.verdict == "READY":
        print(f"GATE: PASS. Протокол: {_rel(out, root)}")
        print("VERDICT: READY")
        return EXIT_READY
    for reason in result.reasons:
        print(f"ПРИЧИНА: {reason}")
    if result.verdict == "REJECT":
        print(f"GATE: REWORK. Согласованный REJECT, блокирующих причин: {len(result.reasons)}.")
        print("VERDICT: REJECT")
        return EXIT_REJECT
    print(f"GATE: BLOCKED. {result.technical_status}: проход закрыт эскалацией.")
    print("VERDICT: ESCALATE")
    return EXIT_ESCALATE


# --------------------------------------------------------------------------- CLI

COMMANDS: tuple[str, ...] = ("sha256", "manifest", "ledger", "freeze", "verify")


def _fail(message: str) -> int:
    """Ошибка использования или данных подкоманды."""
    print(f"ОШИБКА: {message}", file=sys.stderr)
    return EXIT_ESCALATE


def _team_arg(parser: argparse.ArgumentParser) -> None:
    """Общий необязательный позиционный аргумент `team_dir`."""
    parser.add_argument("team_dir", nargs="?", type=Path, default=Path(DEFAULT_TEAM_DIR))


def _cmd_sha256(args: Sequence[str]) -> int:
    """Подкоманда `sha256 <путь>...`: один путь — только хеш, несколько — `хеш  путь`."""
    if not args:
        return _fail("sha256: укажите хотя бы один путь")
    lines: list[str] = []
    for item in args:
        path = Path(item)
        if not path.is_file():
            return _fail(f"sha256: файл не найден: {item}")
        digest = sha256_file(path)
        lines.append(digest if len(args) == 1 else f"{digest}  {item}")
    print("\n".join(lines))
    return 0


def _cmd_manifest(args: Sequence[str], root: Path) -> int:
    """Подкоманда `manifest`."""
    parser = argparse.ArgumentParser(prog="generate_proof.py manifest")
    _team_arg(parser)
    parser.add_argument("--model", default=os.environ.get("OPENCODE_MODEL") or DEFAULT_MODEL)
    parser.add_argument("--cycle", type=int, default=1)
    parser.add_argument("--pass-id", dest="pass_id", default=None)
    ns = parser.parse_args(list(args))
    try:
        print(write_manifest(ns.team_dir, root, ns.model, ns.cycle, ns.pass_id))
    except PanelFormatError as exc:
        return _fail(str(exc))
    return 0


def _cmd_ledger_freeze(command: str, args: Sequence[str], root: Path) -> int:
    """Подкоманды `ledger` и `freeze`."""
    parser = argparse.ArgumentParser(prog=f"generate_proof.py {command}")
    _team_arg(parser)
    ns = parser.parse_args(list(args))
    try:
        action = write_ledger if command == "ledger" else write_freeze
        print(action(ns.team_dir, root))
    except PanelFormatError as exc:
        return _fail(str(exc))
    return 0


def main(argv: Sequence[str] | None = None, root: Path = ROOT) -> int:
    """Точка входа: подкоманда или режим проверки `[team_dir] [out_path]`."""
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args and args[0] in COMMANDS else "verify"
    rest = args[1:] if args and args[0] in COMMANDS else args
    if command == "sha256":
        return _cmd_sha256(rest)
    if command == "manifest":
        return _cmd_manifest(rest, root)
    if command in ("ledger", "freeze"):
        return _cmd_ledger_freeze(command, rest, root)
    parser = argparse.ArgumentParser(prog="generate_proof.py", description=__doc__)
    parser.add_argument("team_dir", nargs="?", type=Path, default=Path(DEFAULT_TEAM_DIR))
    parser.add_argument("out_path", nargs="?", type=Path, default=Path(DEFAULT_OUT_PATH))
    parser.add_argument("--run-checks", action="store_true", dest="run_checks")
    ns = parser.parse_args(rest)
    return run_verify(ns.team_dir, ns.out_path, root, run_checks=ns.run_checks)


if __name__ == "__main__":
    sys.exit(main())
