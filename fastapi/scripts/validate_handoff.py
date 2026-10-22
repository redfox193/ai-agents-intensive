#!/usr/bin/env python3
"""Проверка пакетов Панели техлидов: handoff Кодера, бриф для rework и сама панель.

Использование: `validate_handoff.py [путь ...] [--ledger путь]`.

Без аргументов проверяется эталонный пакет: `.ai-team/handoff-coder.md`, `handoff/coder-01.json`
(если есть), панель `.ai-team/panel/` и `handoff/panel-rework-brief.json` (если есть). Тип
пути определяется так: `*.md` — текстовый handoff Кодера; `*.json` — handoff Кодера
(`author_role=coder`), бриф `panel-rework-brief` (есть `instructions` и `source_findings`)
либо общий формат (`task_id`, `author_role`, `artifacts`, `decisions`, `open_questions`);
каталог — панель. `--ledger` задаёт реестр для сверки покрытия брифа.

Коды выхода: 0 — всё верно, 1 — есть ошибки в проверяемых файлах, 2 — неверное использование.
Только стандартная библиотека.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from generate_proof import (
    ROOT,
    LedgerRow,
    PanelFormatError,
    check_panel,
    parse_ledger_tsv,
    sha256_file,
)

HANDOFF_TITLE = "# Handoff Кодер → Панель техлидов"
HANDOFF_MARKERS: tuple[str, ...] = ("Команды и коды выхода", "Решения", "Риски", "Не смотрел")
CODER_SCHEMA_VERSION = "1.1"
BRIEF_SCHEMA_VERSION = "1.0"
MAX_CYCLE = 5
FIRST_REWORK_CYCLE = 2
CRITERIA_RANGE = range(1, 6)
GENERIC_KEYS: tuple[str, ...] = (
    "task_id",
    "author_role",
    "artifacts",
    "decisions",
    "open_questions",
)
EXCLUDED_REASONS: tuple[str, ...] = ("invalid_after_recheck", "out_of_scope", "foreign_key")
LEDGER_RELATIVE = Path(".ai-team") / "panel" / "findings-ledger.tsv"

_PLACEHOLDER_RE = re.compile(r"<[^<>\n]+>|\bTODO\b|\bTBD\b|\bFIXME\b")
_CODE_SPAN_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
_ROOT_PATH_RE = re.compile(r"(?<![\w.~:/-])/([A-Za-z0-9_.-]+)/")
_HOME_PATH_RE = re.compile(r"(?<!\w)~[/]")
_F_ID_RE = re.compile(r"^F-\d{3,}$")
_RW_RE = re.compile(r"^RW-\d{3}$")
_FU_RE = re.compile(r"^FU-\d{3}$")
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _obj(value: object) -> dict[str, object] | None:
    """JSON-значение как объект."""
    return cast(dict[str, object], value) if isinstance(value, dict) else None


def _arr(value: object) -> list[object] | None:
    """JSON-значение как массив."""
    return cast(list[object], value) if isinstance(value, list) else None


def _is_int(value: object) -> bool:
    """Целое число без булевых значений."""
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_str(value: object) -> bool:
    """Непустая строка."""
    return isinstance(value, str) and bool(value.strip())


def _top_level_dirs() -> frozenset[str]:
    """Имена каталогов корня файловой системы: по ним узнаются абсолютные пути в тексте."""
    try:
        return frozenset(entry.name for entry in Path(Path.cwd().anchor).iterdir())
    except OSError:
        return frozenset()


def has_absolute_path(text: str) -> bool:
    """В тексте есть абсолютный путь (от корня ФС) или путь от домашнего каталога."""
    if _HOME_PATH_RE.search(text):
        return True
    top_level = _top_level_dirs()
    return any(match.group(1) in top_level for match in _ROOT_PATH_RE.finditer(text))


def unsafe_path_reason(value: str) -> str | None:
    """Причина, по которой путь недопустим в handoff: пустой, абсолютный или выходит за корень."""
    if not value.strip():
        return "пустой путь"
    if value.startswith(("/", "\\", "~")) or _WINDOWS_ABS_RE.match(value):
        return "абсолютный путь"
    if ".." in re.split(r"[\\/]+", value):
        return "выход за пределы корня (..)"
    return None


def _walk_strings(value: object) -> list[str]:
    """Все строки внутри JSON-значения."""
    if isinstance(value, str):
        return [value]
    items = _arr(value)
    if items is not None:
        return [text for item in items for text in _walk_strings(item)]
    mapping = _obj(value)
    if mapping is not None:
        return [text for item in mapping.values() for text in _walk_strings(item)]
    return []


def _placeholder_errors(strings: Sequence[str], where: str) -> list[str]:
    """Плейсхолдеры `<...>` и TODO недопустимы в handoff."""
    return [
        f"{where}: плейсхолдер в тексте {text[:60]!r}"
        for text in strings
        if _PLACEHOLDER_RE.search(text)
    ]


def _str_list(data: dict[str, object], key: str, errors: list[str], *, where: str) -> list[str]:
    """Обязательный список строк; нарушения добавляются в `errors`."""
    raw = _arr(data.get(key))
    if raw is None:
        errors.append(f"{where}: поле {key} должно быть списком")
        return []
    if not all(isinstance(item, str) for item in raw):
        errors.append(f"{where}: {key} должен содержать только строки")
        return []
    return [str(item) for item in raw]


def _check_paths(values: Sequence[str], key: str, errors: list[str], *, where: str) -> None:
    """Пути handoff: только относительные, без выхода за корень."""
    for value in values:
        reason = unsafe_path_reason(value)
        if reason is not None:
            errors.append(f"{where}: {key}: {reason}: {value!r}")


# --------------------------------------------------------------------------- handoff Кодера


def _check_ac_and_tests(data: dict[str, object], errors: list[str], where: str) -> None:
    """Поля `ac_results` и `tests`."""
    ac_results = _arr(data.get("ac_results"))
    if ac_results is None:
        errors.append(f"{where}: ac_results должен быть списком")
    else:
        for index, item in enumerate(ac_results):
            entry = _obj(item)
            ok = (
                entry is not None
                and all(_nonempty_str(entry.get(k)) for k in ("id", "status", "command"))
                and _is_int(entry.get("exit_code"))
            )
            if not ok:
                errors.append(f"{where}: ac_results[{index}] без id/status/command/exit_code")
    tests = _arr(data.get("tests"))
    if tests is None:
        errors.append(f"{where}: tests должен быть списком")
        return
    for index, item in enumerate(tests):
        entry = _obj(item)
        if entry is None or not _nonempty_str(entry.get("command")):
            errors.append(f"{where}: tests[{index}] без command")
        elif not _is_int(entry.get("exit_code")) or not isinstance(entry.get("log_ref"), str):
            errors.append(f"{where}: tests[{index}] без exit_code/log_ref")
        else:
            log_ref = str(entry["log_ref"])
            _check_paths([log_ref] if log_ref else [], "log_ref", errors, where=where)


def _check_rw_trace(data: dict[str, object], errors: list[str], where: str) -> None:
    """Для `mode: rework` обязателен `rw_trace` с привязкой к RW-NNN и F-ID."""
    trace = _arr(data.get("rw_trace"))
    if trace is None:
        errors.append(f"{where}: для mode=rework нужен список rw_trace")
        return
    for index, item in enumerate(trace):
        entry = _obj(item)
        tag = f"{where}: rw_trace[{index}]"
        if entry is None:
            errors.append(f"{tag}: ожидался объект")
            continue
        if not isinstance(entry.get("rw_id"), str) or not _RW_RE.match(str(entry["rw_id"])):
            errors.append(f"{tag}: rw_id должен иметь вид RW-NNN")
        findings = _arr(entry.get("source_findings"))
        if not findings or not all(isinstance(f, str) and _F_ID_RE.match(f) for f in findings):
            errors.append(f"{tag}: source_findings — непустой список F-NNN")
        red_green = _obj(entry.get("red_green"))
        if red_green is None or not all(_nonempty_str(red_green.get(k)) for k in ("red", "green")):
            errors.append(f"{tag}: red_green должен содержать непустые red и green")
        files = _str_list(entry, "changed_files", errors, where=tag)
        _check_paths(files, "changed_files", errors, where=tag)


def validate_coder_json(data: dict[str, object]) -> list[str]:
    """Проверяет `handoff/coder-NN.json` (схема 1.1)."""
    where = "handoff Кодера"
    errors: list[str] = []
    if data.get("schema_version") != CODER_SCHEMA_VERSION:
        errors.append(f"{where}: schema_version должен быть {CODER_SCHEMA_VERSION}")
    if not _nonempty_str(data.get("task_id")):
        errors.append(f"{where}: нет task_id")
    if data.get("author_role") != "coder":
        errors.append(f"{where}: author_role должен быть coder")
    cycle = data.get("cycle")
    mode = data.get("mode")
    if not _is_int(cycle) or not isinstance(cycle, int) or not 1 <= cycle <= MAX_CYCLE:
        errors.append(f"{where}: cycle должен быть целым 1..{MAX_CYCLE}")
    if mode not in ("feature", "rework"):
        errors.append(f"{where}: mode должен быть feature или rework")
    elif isinstance(cycle, int) and (mode == "feature") != (cycle == 1):
        errors.append(f"{where}: Цикл 1 — feature, Циклы 2..{MAX_CYCLE} — rework")
    for key in ("changed_files", "artifacts"):
        _check_paths(_str_list(data, key, errors, where=where), key, errors, where=where)
    for key in ("decisions", "open_questions", "risks", "unchanged_checks"):
        _str_list(data, key, errors, where=where)
    _check_ac_and_tests(data, errors, where)
    if mode == "rework":
        _check_rw_trace(data, errors, where)
    errors.extend(_placeholder_errors(_walk_strings(data), where))
    return errors


def validate_generic_json(data: dict[str, object]) -> list[str]:
    """Общий (прежний) формат handoff; `open_questions` может быть пустым списком."""
    where = "handoff"
    errors = [f"{where}: нет обязательной секции {key}" for key in GENERIC_KEYS if key not in data]
    if errors:
        return errors
    decisions = _arr(data["decisions"])
    if not decisions:
        errors.append(f"{where}: секция decisions обязана содержать список решений")
    if _arr(data["open_questions"]) is None:
        errors.append(f"{where}: секция open_questions должна быть списком (пустой допустим)")
    artifacts = _str_list(data, "artifacts", errors, where=where)
    _check_paths(artifacts, "artifacts", errors, where=where)
    errors.extend(_placeholder_errors(_walk_strings(data), where))
    return errors


def _heading_has_body(lines: list[str], index: int, marker: str) -> bool:
    """Раздел-маркер содержит текст: на той же строке после маркера или на следующей."""
    tail = lines[index].split(marker, 1)[1].strip(" :*-—#\t")
    if tail:
        return True
    for following in lines[index + 1 :]:
        if following.strip():
            return not following.lstrip().startswith("#")
    return False


def validate_handoff_md(text: str) -> list[str]:
    """Проверяет текстовую проекцию handoff Кодера."""
    where = "handoff-coder.md"
    errors: list[str] = []
    lines = text.split("\n")
    first = next((ln.strip() for ln in lines if ln.strip()), "")
    if first != HANDOFF_TITLE:
        errors.append(f"{where}: заголовок должен быть `{HANDOFF_TITLE}`")
    for marker in HANDOFF_MARKERS:
        index = next((i for i, ln in enumerate(lines) if marker in ln), None)
        if index is None:
            errors.append(f"{where}: нет раздела «{marker}»")
        elif not _heading_has_body(lines, index, marker):
            errors.append(f"{where}: раздел «{marker}» пуст")
    prose = _CODE_SPAN_RE.sub("", text)
    errors.extend(_placeholder_errors(prose.split("\n"), where))
    if has_absolute_path(text):
        errors.append(f"{where}: абсолютные пути недопустимы, нужны относительные")
    return errors


# --------------------------------------------------------------------------- бриф для rework


def _brief_buckets(
    data: dict[str, object], errors: list[str]
) -> tuple[dict[str, str], list[str], list[str]]:
    """Корзины брифа: (F-ID -> корзина), исходные F-ID брифа, F-ID, учтённые в корзинах."""
    placed: dict[str, str] = {}
    counted: list[str] = []

    def take(f_ids: object, bucket: str, tag: str) -> None:
        values = _arr(f_ids)
        if not values or not all(isinstance(f, str) and _F_ID_RE.match(f) for f in values):
            errors.append(f"{tag}: source_findings — непустой список F-NNN")
            return
        for f_id in map(str, values):
            counted.append(f_id)
            if f_id in placed:
                errors.append(f"{f_id}: встречается больше одного раза ({placed[f_id]}, {bucket})")
            placed[f_id] = bucket

    for index, item in enumerate(_arr(data.get("instructions")) or []):
        entry = _obj(item)
        if entry is not None:
            take(entry.get("source_findings"), "instructions", f"instructions[{index}]")
    for index, item in enumerate(_arr(data.get("non_blocking_followups")) or []):
        entry = _obj(item)
        if entry is not None:
            take(entry.get("source_findings"), "followups", f"non_blocking_followups[{index}]")
    for index, item in enumerate(_arr(data.get("excluded")) or []):
        entry = _obj(item)
        if entry is not None:
            take([entry.get("source_finding")], "excluded", f"excluded[{index}]")
    declared = [str(f) for f in _arr(data.get("source_findings")) or [] if isinstance(f, str)]
    return placed, declared, counted


def _check_instruction(index: int, item: object, seen_ids: set[str], errors: list[str]) -> None:
    """Поля одной blocking-инструкции `RW-NNN`."""
    tag = f"instructions[{index}]"
    entry = _obj(item)
    if entry is None:
        errors.append(f"{tag}: ожидался объект")
        return
    rw_id = entry.get("id")
    if not isinstance(rw_id, str) or not _RW_RE.match(rw_id):
        errors.append(f"{tag}: id должен иметь вид RW-NNN")
    elif rw_id in seen_ids:
        errors.append(f"{tag}: повторный id {rw_id}")
    else:
        seen_ids.add(rw_id)
    if entry.get("disposition") != "blocking":
        errors.append(f"{tag}: disposition должен быть blocking")
    criterion = entry.get("criterion")
    if (
        not isinstance(criterion, int)
        or isinstance(criterion, bool)
        or criterion not in CRITERIA_RANGE
    ):
        errors.append(f"{tag}: criterion должен быть целым 1..5")
    file_value = entry.get("file")
    if not isinstance(file_value, str):
        errors.append(f"{tag}: file должен быть строкой")
    else:
        _check_paths([file_value], "file", errors, where=tag)
    hint = entry.get("line_hint")
    if not (_is_int(hint) or _nonempty_str(hint)):
        errors.append(f"{tag}: line_hint — целое или непустая строка")
    for key in ("rule_ref", "action", "acceptance", "source", "evidence"):
        if not _nonempty_str(entry.get(key)):
            errors.append(f"{tag}: нет непустого поля {key}")


def _check_brief_lists(data: dict[str, object], errors: list[str]) -> None:
    """Структура корзин брифа и `terminal_objections`."""
    instructions = _arr(data.get("instructions"))
    followups = _arr(data.get("non_blocking_followups"))
    excluded = _arr(data.get("excluded"))
    objections = _arr(data.get("terminal_objections"))
    for key, value in (
        ("instructions", instructions),
        ("non_blocking_followups", followups),
        ("excluded", excluded),
        ("terminal_objections", objections),
    ):
        if value is None:
            errors.append(f"brief: поле {key} должно быть списком")
    seen: set[str] = set()
    for index, item in enumerate(instructions or []):
        _check_instruction(index, item, seen, errors)
    fu_seen: set[str] = set()
    for index, item in enumerate(followups or []):
        entry = _obj(item)
        tag = f"non_blocking_followups[{index}]"
        if entry is None:
            errors.append(f"{tag}: ожидался объект")
            continue
        fu_id = entry.get("id")
        if not isinstance(fu_id, str) or not _FU_RE.match(fu_id) or fu_id in fu_seen:
            errors.append(f"{tag}: id должен иметь вид FU-NNN и не повторяться")
        else:
            fu_seen.add(fu_id)
        for key in ("evidence", "action", "acceptance"):
            if not _nonempty_str(entry.get(key)):
                errors.append(f"{tag}: нет непустого поля {key}")
    for index, item in enumerate(excluded or []):
        entry = _obj(item)
        if entry is None or not _nonempty_str(entry.get("evidence")):
            errors.append(f"excluded[{index}]: нужен объект с непустым evidence")
    for index, item in enumerate(objections or []):
        entry = _obj(item)
        if entry is None or not all(
            _nonempty_str(entry.get(k)) for k in ("judge", "evidence", "defect")
        ):
            errors.append(f"terminal_objections[{index}]: нужны непустые judge, evidence, defect")
    if instructions is not None and not instructions and not objections:
        errors.append(
            "brief: пустые instructions допустимы только при непустых terminal_objections"
        )


def _check_excluded_reasons(
    data: dict[str, object], known: set[str], errors: list[str]
) -> dict[str, str]:
    """Закрытый список причин `excluded`; возвращает F-ID -> причина."""
    reasons: dict[str, str] = {}
    duplicates: dict[str, str] = {}
    for index, item in enumerate(_arr(data.get("excluded")) or []):
        entry = _obj(item)
        if entry is None:
            continue
        source, reason = entry.get("source_finding"), entry.get("reason")
        tag = f"excluded[{index}]"
        if not isinstance(source, str) or not isinstance(reason, str):
            errors.append(f"{tag}: нужны строки source_finding и reason")
            continue
        reasons[source] = reason
        if reason.startswith("duplicate_of:"):
            target = reason.removeprefix("duplicate_of:")
            if target == source:
                errors.append(f"{tag}: {source} не может быть дублем самой себя")
            elif target not in known:
                errors.append(f"{tag}: duplicate_of указывает на несуществующую {target}")
            else:
                duplicates[source] = target
        elif reason not in EXCLUDED_REASONS:
            errors.append(f"{tag}: недопустимая причина {reason!r}")
    for start in duplicates:
        node, hops = start, 0
        while node in duplicates and hops <= len(duplicates):
            node, hops = duplicates[node], hops + 1
        if hops > len(duplicates):
            errors.append(f"excluded: цикл duplicate_of от {start}")
            break
    return reasons


def _check_against_ledger(
    placed: dict[str, str], reasons: dict[str, str], rows: Sequence[LedgerRow], errors: list[str]
) -> None:
    """Классификация находок реестра по корзинам: тяжесть и статус задают корзину."""
    for row in rows:
        bucket = placed.get(row.f_id)
        blocking = row.severity in ("BLOCKER", "IMPORTANT") and row.status != "WITHDRAWN"
        if bucket == "instructions" and not blocking:
            errors.append(
                f"{row.f_id}: не blocking ({row.severity}/{row.status}), но в instructions"
            )
        elif bucket == "followups" and (row.severity != "MINOR" or row.status == "WITHDRAWN"):
            errors.append(f"{row.f_id}: в followups допустимы только MINOR OPEN/AGREED")
        elif bucket == "excluded" and row.status == "WITHDRAWN":
            if reasons.get(row.f_id) != "invalid_after_recheck":
                errors.append(f"{row.f_id}: WITHDRAWN исключается с причиной invalid_after_recheck")


def validate_brief(
    data: dict[str, object], rows: Sequence[LedgerRow] | None, ledger_sha: str | None
) -> list[str]:
    """Проверяет `panel-rework-brief.json`; с реестром — ещё и покрытие, привязку и классы."""
    errors: list[str] = []
    if data.get("schema_version") != BRIEF_SCHEMA_VERSION:
        errors.append(f"brief: schema_version должен быть {BRIEF_SCHEMA_VERSION}")
    for key in ("task_id", "source_pass_id", "ledger_hash"):
        if not _nonempty_str(data.get(key)):
            errors.append(f"brief: нет непустой строки {key}")
    cycle = data.get("cycle")
    if (
        not isinstance(cycle, int)
        or isinstance(cycle, bool)
        or not FIRST_REWORK_CYCLE <= cycle <= MAX_CYCLE
    ):
        errors.append(f"brief: cycle должен быть целым {FIRST_REWORK_CYCLE}..{MAX_CYCLE}")
    _check_brief_lists(data, errors)
    placed, declared, counted = _brief_buckets(data, errors)
    if len(set(declared)) != len(declared) or not all(_F_ID_RE.match(f) for f in declared):
        errors.append("brief: source_findings содержит дубли или неверные F-NNN")
    if not _is_int(data.get("findings_total")) or data.get("findings_total") != len(declared):
        errors.append("brief: findings_total не равен числу source_findings")
    lost = sorted(set(declared) - set(counted))
    stray = sorted(set(counted) - set(declared))
    errors.extend(f"{f_id}: потерян (нет ни в одной корзине)" for f_id in lost)
    errors.extend(f"{f_id}: есть в корзине, но нет в source_findings" for f_id in stray)
    known = {row.f_id for row in rows} if rows is not None else set(declared)
    reasons = _check_excluded_reasons(data, known, errors)
    if rows is not None:
        if set(declared) != known:
            errors.append("brief: source_findings не совпадает с множеством F-ID реестра")
        if data.get("findings_total") != len(rows):
            errors.append("brief: findings_total не равен числу строк реестра")
        if ledger_sha is not None and data.get("ledger_hash") != ledger_sha:
            errors.append("brief: ledger_hash не совпал с sha256 реестра (реестр пересобран)")
        _check_against_ledger(placed, reasons, rows, errors)
    return errors


# --------------------------------------------------------------------------- панель и диспетчер


def check_brief_source(data: dict[str, object], ledger_file: Path) -> list[str]:
    """Бриф ссылается на проход из соседнего `manifest.json`: тот же pass_id, цикл + 1."""
    manifest = ledger_file.parent / "manifest.json"
    if not ledger_file.is_file() or not manifest.is_file():
        return []
    try:
        raw: object = json.loads(manifest.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return [f"{manifest.name}: паспорт прохода нечитаем"]
    passport = _obj(raw)
    if passport is None:
        return [f"{manifest.name}: ожидался JSON-объект"]
    errors: list[str] = []
    if data.get("source_pass_id") != passport.get("pass_id"):
        errors.append("brief: source_pass_id не совпал с pass_id паспорта прохода")
    source_cycle = passport.get("cycle")
    if (
        _is_int(source_cycle)
        and isinstance(source_cycle, int)
        and data.get("cycle") != source_cycle + 1
    ):
        errors.append(f"brief: cycle должен быть циклом прохода + 1 ({source_cycle + 1})")
    return errors


def _load_ledger(
    ledger: Path | None, root: Path
) -> tuple[list[LedgerRow] | None, str | None, list[str]]:
    """Реестр для сверки: явный `--ledger` обязателен, умолчание берётся, если файл есть."""
    path = ledger if ledger is not None else root / LEDGER_RELATIVE
    if not path.is_file():
        if ledger is not None:
            return None, None, [f"реестр не найден: {ledger}"]
        return None, None, []
    try:
        rows = parse_ledger_tsv(path.read_text(encoding="utf-8"))
    except (PanelFormatError, OSError, UnicodeDecodeError) as exc:
        return None, None, [f"реестр {path.name}: {exc}"]
    return rows, sha256_file(path), []


def _validate_panel_dir(path: Path, root: Path | None) -> list[str]:
    """Структурная проверка панели без записи файлов."""
    team = path.parent if path.name == "panel" else path
    base = root if root is not None else team.resolve().parent
    result = check_panel(team, base)
    if result.technical_status is None:
        return []
    return [f"{result.technical_status}: {reason}" for reason in result.reasons]


def _validate_json(path: Path, ledger: Path | None, root: Path | None) -> tuple[str, list[str]]:
    """Разбор и проверка JSON-файла с автоопределением типа."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return "json", [f"{path}: файл нечитаем ({exc.__class__.__name__})"]
    except json.JSONDecodeError as exc:
        return "json", [f"{path}: невалидный JSON ({exc.msg})"]
    data = _obj(raw)
    if data is None:
        return "json", [f"{path}: ожидался JSON-объект"]
    if data.get("author_role") == "coder" or "mode" in data:
        return "handoff Кодера (JSON)", validate_coder_json(data)
    if "instructions" in data and "source_findings" in data:
        base = root if root is not None else path.resolve().parent.parent
        rows, sha, load_errors = _load_ledger(ledger, base)
        if load_errors:
            return "panel-rework-brief", load_errors
        errors = validate_brief(data, rows, sha)
        ledger_file = ledger if ledger is not None else base / LEDGER_RELATIVE
        return "panel-rework-brief", [*errors, *check_brief_source(data, ledger_file)]
    return "handoff (общий формат)", validate_generic_json(data)


def _validate(path: Path, ledger: Path | None, root: Path | None) -> tuple[str, list[str]]:
    """Проверяет один путь; возвращает (тип, ошибки)."""
    if not path.exists():
        return "файл", [f"Файл пакета не найден: {path}"]
    if path.is_dir():
        return "панель", _validate_panel_dir(path, root)
    if path.suffix == ".md":
        try:
            return "handoff Кодера (Markdown)", validate_handoff_md(
                path.read_text(encoding="utf-8")
            )
        except OSError, UnicodeDecodeError:
            return "handoff Кодера (Markdown)", [f"{path}: файл нечитаем"]
    if path.suffix == ".json":
        return _validate_json(path, ledger, root)
    return "файл", [f"{path}: поддерживаются только *.json, *.md и каталоги панели"]


def validate_path(
    path: Path | str, ledger: Path | str | None = None, root: Path | None = None
) -> list[str]:
    """Проверяет handoff, бриф или панель по пути; возвращает список ошибок (пусто — верно).

    Args:
        path: `*.json`, `*.md` или каталог панели (`.ai-team` либо `.ai-team/panel`).
        ledger: реестр для сверки покрытия брифа (по умолчанию `.ai-team/panel/...`).
        root: корень проекта; по умолчанию выводится из расположения файла.
    """
    return _validate(Path(path), Path(ledger) if ledger is not None else None, root)[1]


def _default_targets(root: Path) -> list[Path]:
    """Эталонный пакет для запуска без аргументов."""
    candidates = [
        root / ".ai-team" / "handoff-coder.md",
        root / "handoff" / "coder-01.json",
        root / ".ai-team",
        root / "handoff" / "panel-rework-brief.json",
    ]
    required = {candidates[0], candidates[2]}
    return [p for p in candidates if p in required or p.exists()]


def _report(path: Path, ledger: Path | None, root: Path | None, out: Callable[[str], None]) -> bool:
    """Проверяет путь, печатает итог; True — без ошибок."""
    kind, errors = _validate(path, ledger, root)
    for error in errors:
        print(f"ОШИБКА: {error}", file=sys.stderr)
    if errors:
        return False
    shown = path
    if root is not None and path.is_absolute():
        try:
            shown = path.relative_to(root)
        except ValueError:
            shown = path
    out(f"УСПЕХ: {shown} — {kind} соответствует контракту.")
    if kind == "panel-rework-brief":
        data = _obj(json.loads(path.read_text(encoding="utf-8")))
        count = len(_arr(data.get("instructions")) or []) if data is not None else 0
        out(f"VALID n_instructions={count}")
    return True


def main(argv: Sequence[str] | None = None, root: Path = ROOT) -> int:
    """Точка входа: пути из аргументов либо эталонный пакет `root`."""
    args = list(sys.argv[1:] if argv is None else argv)
    ledger: Path | None = None
    paths: list[Path] = []
    index = 0
    while index < len(args):
        if args[index] == "--ledger":
            if index + 1 >= len(args):
                print(
                    "Использование: validate_handoff.py [путь ...] [--ledger путь]", file=sys.stderr
                )
                return 2
            ledger = Path(args[index + 1])
            index += 2
        elif args[index].startswith("--"):
            print(f"Неизвестный флаг {args[index]}", file=sys.stderr)
            return 2
        else:
            paths.append(Path(args[index]))
            index += 1
    default_run = not paths
    targets = _default_targets(root) if default_run else paths
    ok = all([_report(p, ledger, root if default_run else None, print) for p in targets])
    if ok:
        print("GATE: PASS")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
