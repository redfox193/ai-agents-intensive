"""Контрактные тесты `validate_handoff.py`: handoff Кодера, бриф для rework и панель.

Файлы создаются во временной копии эталона; для брифа реестр передаётся флагом `--ledger`
либо берётся из `.ai-team/panel/` копии.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import generate_proof as gp
import pytest
import validate_handoff as vh

if TYPE_CHECKING:
    from conftest import PanelKit

Json = dict[str, object]
HANDOFF_JSON = "handoff/coder-01.json"
BRIEF_JSON = "handoff/panel-rework-brief.json"

LEDGER_ROWS = [
    gp.LedgerRow(
        "F-001",
        "IMPORTANT",
        "judge-1",
        "app/services/link.py:42",
        "утечка",
        "AGREED",
        "D3:agree-3/3",
    ),
    gp.LedgerRow(
        "F-002",
        "MINOR",
        "judge-2",
        "docs/risk-plan-LINK-42.md:10",
        "формулировка",
        "AGREED",
        "D2:agree-3/3",
    ),
    gp.LedgerRow(
        "F-003",
        "IMPORTANT",
        "judge-3",
        "app/main.py:7",
        "снята",
        "WITHDRAWN",
        "D1:withdrawn-by-author",
    ),
]


def coder_json() -> Json:
    """Корректный handoff Кодера первого цикла."""
    return {
        "schema_version": "1.1",
        "task_id": "LINK-42",
        "author_role": "coder",
        "cycle": 1,
        "mode": "feature",
        "changed_files": ["app/services/link.py", "tests/flat_api/test_links.py"],
        "artifacts": [".ai-team/handoff-coder.md"],
        "decisions": ["Проверка активности стоит до инкремента счётчика"],
        "open_questions": [],
        "ac_results": [
            {"id": "AC-1", "status": "pass", "command": "uv run pytest -q", "exit_code": 0}
        ],
        "tests": [
            {
                "command": "uv run pytest -q",
                "exit_code": 0,
                "log_ref": "handoff/pipeline-execution.log",
            }
        ],
        "risks": ["Нагрузка на PostgreSQL не проверялась"],
        "unchanged_checks": ["tests/flat_api/test_characterization.py"],
    }


def rework_json() -> Json:
    """Корректный handoff Кодера в режиме rework (Цикл 2)."""
    data = coder_json()
    data.update(
        cycle=2,
        mode="rework",
        rw_trace=[
            {
                "rw_id": "RW-001",
                "source_findings": ["F-001"],
                "red_green": {"red": "uv run pytest -q: 1 failed", "green": "uv run pytest -q: 0"},
                "changed_files": ["app/services/link.py"],
            }
        ],
    )
    return data


def brief_json(ledger_sha: str) -> Json:
    """Корректный бриф для реестра `LEDGER_ROWS`."""
    return {
        "schema_version": "1.0",
        "task_id": "LINK-42",
        "cycle": 2,
        "source_pass_id": "pass-001",
        "ledger_hash": ledger_sha,
        "instructions": [
            {
                "id": "RW-001",
                "source_findings": ["F-001"],
                "disposition": "blocking",
                "criterion": 5,
                "file": "app/services/link.py",
                "line_hint": 42,
                "rule_ref": "docs/gate-rubric.md",
                "action": "Убрать утечку",
                "acceptance": "uv run pytest tests/flat_api -q",
                "source": "judge-1 / R1",
                "evidence": "app/services/link.py:42",
            }
        ],
        "non_blocking_followups": [
            {
                "id": "FU-001",
                "source_findings": ["F-002"],
                "evidence": "docs/risk-plan-LINK-42.md:10",
                "action": "Уточнить формулировку",
                "acceptance": "ручная сверка риск-плана",
            }
        ],
        "excluded": [
            {
                "source_finding": "F-003",
                "evidence": "d1/judge-1.md",
                "reason": "invalid_after_recheck",
            }
        ],
        "findings_total": 3,
        "source_findings": ["F-001", "F-002", "F-003"],
        "terminal_objections": [],
    }


def write_json(path: Path, data: Json) -> Path:
    """Записывает JSON-файл, создавая каталог."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_ledger(path: Path, rows: list[gp.LedgerRow] | None = None) -> str:
    """Записывает реестр и возвращает его sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        gp.render_ledger_tsv(rows if rows is not None else LEDGER_ROWS), encoding="utf-8"
    )
    return gp.sha256_file(path)


def absolute_path(*parts: str) -> str:
    """Абсолютный путь из частей (литерал пути в исходнике не нужен)."""
    return "/" + "/".join(parts)


def errors_text(errors: list[str]) -> str:
    """Список ошибок одной строкой."""
    return "\n".join(errors)


# --------------------------------------------------------------------------- пакет по умолчанию


def test_default_run_validates_reference_package(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    assert vh.main([], kit.root) == 0
    captured = capsys.readouterr()
    assert "УСПЕХ:" in captured.out
    assert captured.out.strip().splitlines()[-1] == "GATE: PASS"
    assert captured.err == ""


def test_default_run_without_arguments_is_not_a_usage_error(kit: PanelKit) -> None:
    assert vh.main([], kit.root) != 2


def test_default_run_fails_without_handoff(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    kit.delete(".ai-team/handoff-coder.md")
    assert vh.main([], kit.root) == 1
    assert "ОШИБКА: Файл пакета не найден" in capsys.readouterr().err


def test_default_run_checks_panel_structure(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    kit.delete(".ai-team/panel/c1/judge-3.md")
    assert vh.main([], kit.root) == 1
    assert "QUORUM_UNAVAILABLE" in capsys.readouterr().err


def test_default_run_does_not_write_files(kit: PanelKit) -> None:
    kit.delete(".ai-team/consensus-proof.json")
    kit.delete(".ai-team/verdict.md")
    assert vh.main([], kit.root) == 0
    assert not (kit.team / "consensus-proof.json").exists()
    assert not (kit.team / "verdict.md").exists()
    assert not (kit.root / "handoff").exists()


def test_default_run_includes_coder_json_and_brief_when_present(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    write_json(kit.path(HANDOFF_JSON), coder_json())
    ledger_sha = gp.sha256_file(kit.panel / "findings-ledger.tsv")
    brief = brief_json(ledger_sha)
    brief["source_pass_id"] = json.loads(kit.read(".ai-team/panel/manifest.json"))["pass_id"]
    brief.update(
        instructions=[],
        non_blocking_followups=[
            {
                "id": "FU-001",
                "source_findings": ["F-001", "F-003", "F-004", "F-005"],
                "evidence": "d3/judge-1.md",
                "action": "Выполнить доработки уровня MINOR",
                "acceptance": "ручная сверка реестра",
            }
        ],
        excluded=[
            {
                "source_finding": "F-002",
                "evidence": "d1/judge-1.md",
                "reason": "invalid_after_recheck",
            }
        ],
        findings_total=5,
        source_findings=["F-001", "F-002", "F-003", "F-004", "F-005"],
        terminal_objections=[
            {"judge": "judge-2", "evidence": "app/main.py:41", "defect": "возражение C1"}
        ],
    )
    write_json(kit.path(BRIEF_JSON), brief)
    assert vh.main([], kit.root) == 0
    out = capsys.readouterr().out
    assert "handoff Кодера (JSON)" in out
    assert "VALID n_instructions=0" in out


def test_default_run_reports_invalid_optional_file(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = coder_json()
    broken["changed_files"] = ["../outside.py"]
    write_json(kit.path(HANDOFF_JSON), broken)
    assert vh.main([], kit.root) == 1
    assert "выход за пределы корня" in capsys.readouterr().err


def test_script_runs_without_arguments_from_scripts_directory(kit: PanelKit) -> None:
    shutil.copytree(
        Path(vh.__file__).resolve().parent,
        kit.root / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", "test_*", "conftest.py"),
    )
    done = subprocess.run(
        [sys.executable, "scripts/validate_handoff.py"],
        cwd=kit.root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip().splitlines()[-1] == "GATE: PASS"


# --------------------------------------------------------------------------- handoff Кодера (JSON)


def test_valid_coder_json_with_empty_open_questions(tmp_path: Path) -> None:
    path = write_json(tmp_path / "coder-01.json", coder_json())
    assert vh.validate_path(path) == []


def test_valid_rework_json(tmp_path: Path) -> None:
    path = write_json(tmp_path / "coder-02.json", rework_json())
    assert vh.validate_path(path) == []


def drop(key: str) -> Callable[[Json], None]:
    """Мутация: убрать поле."""

    def mutate(data: Json) -> None:
        del data[key]

    return mutate


def put(key: str, value: object) -> Callable[[Json], None]:
    """Мутация: задать значение поля."""

    def mutate(data: Json) -> None:
        data[key] = value

    return mutate


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        (drop("changed_files"), "changed_files должно быть списком"),
        (drop("tests"), "tests должен быть списком"),
        (drop("ac_results"), "ac_results должен быть списком"),
        (put("schema_version", "1.0"), "schema_version"),
        (put("author_role", "judge"), "author_role"),
        (put("cycle", 6), "cycle должен быть целым 1..5"),
        (put("cycle", 0), "cycle должен быть целым 1..5"),
        (put("cycle", True), "cycle должен быть целым 1..5"),
        (put("mode", "fix"), "mode должен быть feature или rework"),
        (put("mode", "rework"), "Цикл 1 — feature"),
        (put("open_questions", "нет"), "open_questions должно быть списком"),
        (put("decisions", [1, 2]), "decisions должен содержать только строки"),
        (put("task_id", ""), "нет task_id"),
        (put("ac_results", [{"id": "AC-1", "status": "pass", "command": "x"}]), "ac_results[0]"),
        (put("tests", [{"command": "x", "exit_code": 0}]), "tests[0] без exit_code/log_ref"),
        (put("risks", ["TODO описать риски"]), "плейсхолдер"),
        (put("decisions", ["Решение: <описание>"]), "плейсхолдер"),
    ],
)
def test_invalid_coder_json(
    tmp_path: Path, mutation: Callable[[Json], None], fragment: str
) -> None:
    data = coder_json()
    mutation(data)
    errors = vh.validate_path(write_json(tmp_path / "coder-01.json", data))
    assert errors, "ожидалась ошибка"
    assert fragment in errors_text(errors), errors_text(errors)


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("../etc/passwd", "выход за пределы корня"),
        ("app/../../secret.txt", "выход за пределы корня"),
        ("..\\win\\evil.py", "выход за пределы корня"),
        ("/etc/passwd", "абсолютный путь"),
        ("~" + "/work/file.py", "абсолютный путь"),
        ("C:\\Users\\x\\file.py", "абсолютный путь"),
        ("\\\\server\\share", "абсолютный путь"),
        ("", "пустой путь"),
    ],
)
@pytest.mark.parametrize("field", ["changed_files", "artifacts"])
def test_path_escape_in_coder_json(tmp_path: Path, field: str, value: str, fragment: str) -> None:
    data = coder_json()
    data[field] = ["app/ok.py", value]
    errors = vh.validate_path(write_json(tmp_path / "coder-01.json", data))
    assert fragment in errors_text(errors), errors_text(errors)
    assert field in errors_text(errors)


def test_path_escape_in_log_ref_and_rw_trace(tmp_path: Path) -> None:
    data = rework_json()
    data["tests"] = [{"command": "x", "exit_code": 0, "log_ref": "/var/log/x.log"}]
    trace = data["rw_trace"]
    assert isinstance(trace, list)
    trace[0]["changed_files"] = ["../escape.py"]
    errors_joined = errors_text(vh.validate_path(write_json(tmp_path / "coder-02.json", data)))
    assert "log_ref: абсолютный путь" in errors_joined
    assert "changed_files: выход за пределы корня" in errors_joined


def test_rework_requires_rw_trace(tmp_path: Path) -> None:
    data = rework_json()
    del data["rw_trace"]
    errors = vh.validate_path(write_json(tmp_path / "coder-02.json", data))
    assert "нужен список rw_trace" in errors_text(errors)


@pytest.mark.parametrize(
    ("patch", "fragment"),
    [
        ({"rw_id": "RW-1"}, "rw_id должен иметь вид RW-NNN"),
        ({"source_findings": []}, "source_findings"),
        ({"source_findings": ["F-1"]}, "source_findings"),
        ({"red_green": {"red": "x"}}, "red_green"),
        ({"red_green": "нет"}, "red_green"),
    ],
)
def test_invalid_rw_trace_entry(tmp_path: Path, patch: Json, fragment: str) -> None:
    data = rework_json()
    trace = copy.deepcopy(data["rw_trace"])
    assert isinstance(trace, list)
    trace[0].update(patch)
    data["rw_trace"] = trace
    errors = vh.validate_path(write_json(tmp_path / "coder-02.json", data))
    assert fragment in errors_text(errors), errors_text(errors)


# --------------------------------------------------------------------------- общий формат


def generic_json() -> Json:
    """Прежний общий формат handoff."""
    return {
        "task_id": "LINK-42",
        "author_role": "coder",
        "artifacts": ["app/main.py"],
        "decisions": ["Редирект отдаёт 307"],
        "open_questions": [],
    }


def test_generic_json_with_empty_open_questions_is_valid(tmp_path: Path) -> None:
    data = generic_json()
    data.pop("author_role")
    data["author_role"] = "other-role"
    assert vh.validate_path(write_json(tmp_path / "handoff.json", data)) == []


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        (drop("decisions"), "нет обязательной секции decisions"),
        (drop("task_id"), "нет обязательной секции task_id"),
        (put("decisions", []), "decisions обязана содержать список решений"),
        (put("open_questions", "нет"), "open_questions должна быть списком"),
        (put("artifacts", ["../x"]), "выход за пределы корня"),
        (put("artifacts", "app/main.py"), "artifacts должно быть списком"),
    ],
)
def test_invalid_generic_json(
    tmp_path: Path, mutation: Callable[[Json], None], fragment: str
) -> None:
    data = generic_json()
    data["author_role"] = "other"
    mutation(data)
    errors = vh.validate_path(write_json(tmp_path / "handoff.json", data))
    assert fragment in errors_text(errors), errors_text(errors)


def test_broken_json_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{ не json", encoding="utf-8")
    assert "невалидный JSON" in errors_text(vh.validate_path(path))
    path.write_text("[1, 2]", encoding="utf-8")
    assert "ожидался JSON-объект" in errors_text(vh.validate_path(path))


def test_missing_path_and_unsupported_suffix(tmp_path: Path) -> None:
    assert "Файл пакета не найден" in errors_text(vh.validate_path(tmp_path / "нет.json"))
    other = tmp_path / "notes.txt"
    other.write_text("x", encoding="utf-8")
    assert "поддерживаются только" in errors_text(vh.validate_path(other))


# --------------------------------------------------------------------------- handoff Кодера (Markdown)


def test_reference_markdown_handoff_is_valid(kit: PanelKit) -> None:
    assert vh.validate_path(kit.path(".ai-team/handoff-coder.md")) == []


def md_with(kit: PanelKit, old: str, new: str) -> list[str]:
    """Правит эталонный handoff-coder.md и проверяет его."""
    kit.replace(".ai-team/handoff-coder.md", old, new)
    return vh.validate_path(kit.path(".ai-team/handoff-coder.md"))


def test_markdown_old_title_is_rejected(kit: PanelKit) -> None:
    errors = md_with(kit, "# Handoff Кодер → Панель техлидов", "# Handoff Кодер → Ревью")
    assert "заголовок должен быть" in errors_text(errors)


@pytest.mark.parametrize("marker", ["Команды и коды выхода", "Решения", "Риски", "Не смотрел"])
def test_markdown_missing_marker(kit: PanelKit, marker: str) -> None:
    text = kit.read(".ai-team/handoff-coder.md").replace(marker, "Раздел")
    kit.write(".ai-team/handoff-coder.md", text)
    errors = vh.validate_path(kit.path(".ai-team/handoff-coder.md"))
    assert f"нет раздела «{marker}»" in errors_text(errors)


def test_markdown_empty_section(kit: PanelKit) -> None:
    errors = md_with(kit, "## Не смотрел\n", "## Не смотрел\n\n## Ещё\n")
    assert "раздел «Не смотрел» пуст" in errors_text(errors)


def test_markdown_placeholder_and_todo(kit: PanelKit) -> None:
    assert "плейсхолдер" in errors_text(md_with(kit, "Задача: LINK-42", "Задача: <ключ задачи>"))


def test_markdown_todo_marker(kit: PanelKit) -> None:
    assert "плейсхолдер" in errors_text(
        md_with(kit, "Нагрузочное поведение", "TODO: Нагрузочное поведение")
    )


def test_markdown_placeholder_inside_code_span_is_allowed(kit: PanelKit) -> None:
    assert md_with(kit, "Задача: LINK-42", "Задача: LINK-42 (`<path>` в примере)") == []


def test_markdown_absolute_path_is_rejected(kit: PanelKit) -> None:
    errors = md_with(
        kit, "`app/models/link.py`", f"`{absolute_path('home', 'user', 'app', 'link.py')}`"
    )
    assert "абсолютные пути недопустимы" in errors_text(errors)


# --------------------------------------------------------------------------- panel-rework-brief


@pytest.fixture
def ledger_path(tmp_path: Path) -> tuple[Path, str]:
    """Реестр для проверки брифа и его sha256."""
    path = tmp_path / "ledger" / "findings-ledger.tsv"
    return path, write_ledger(path)


def check_brief(tmp_path: Path, data: Json, ledger: Path) -> list[str]:
    """Записывает бриф и проверяет его против реестра."""
    return vh.validate_path(
        write_json(tmp_path / "handoff" / "panel-rework-brief.json", data), ledger
    )


def test_valid_brief(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    ledger, sha = ledger_path
    assert check_brief(tmp_path, brief_json(sha), ledger) == []


def test_brief_is_detected_without_author_role(
    tmp_path: Path, ledger_path: tuple[Path, str]
) -> None:
    ledger, sha = ledger_path
    data = brief_json(sha)
    assert "author_role" not in data
    assert check_brief(tmp_path, data, ledger) == []


def brief_error(
    tmp_path: Path, ledger_path: tuple[Path, str], mutate: Callable[[Json], None]
) -> str:
    """Применяет мутацию к корректному брифу и возвращает текст ошибок."""
    ledger, sha = ledger_path
    data = brief_json(sha)
    mutate(data)
    errors = check_brief(tmp_path, data, ledger)
    assert errors, "ожидалась ошибка"
    return errors_text(errors)


def test_brief_lost_finding(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    def mutate(data: Json) -> None:
        data["excluded"] = []

    assert "F-003: потерян (нет ни в одной корзине)" in brief_error(tmp_path, ledger_path, mutate)


def test_brief_finding_in_two_buckets(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    def mutate(data: Json) -> None:
        data["excluded"] = [
            {"source_finding": "F-003", "evidence": "x", "reason": "invalid_after_recheck"},
            {"source_finding": "F-001", "evidence": "x", "reason": "out_of_scope"},
        ]

    assert "F-001: встречается больше одного раза" in brief_error(tmp_path, ledger_path, mutate)


def test_brief_finding_twice_in_one_bucket(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    def mutate(data: Json) -> None:
        data["non_blocking_followups"] = [
            {
                "id": "FU-001",
                "source_findings": ["F-002", "F-002"],
                "evidence": "x",
                "action": "a",
                "acceptance": "b",
            }
        ]

    assert "F-002: встречается больше одного раза" in brief_error(tmp_path, ledger_path, mutate)


def test_brief_finding_outside_ledger(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    def mutate(data: Json) -> None:
        data["source_findings"] = ["F-001", "F-002", "F-003", "F-004"]
        data["findings_total"] = 4
        data["excluded"] = [
            {"source_finding": "F-003", "evidence": "x", "reason": "invalid_after_recheck"},
            {"source_finding": "F-004", "evidence": "x", "reason": "out_of_scope"},
        ]

    text = brief_error(tmp_path, ledger_path, mutate)
    assert "не совпадает с множеством F-ID реестра" in text
    assert "findings_total не равен числу строк реестра" in text


def test_brief_wrong_findings_total(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    assert "findings_total" in brief_error(
        tmp_path, ledger_path, lambda d: d.update(findings_total=4)
    )


def test_brief_stale_ledger_hash(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    assert "ledger_hash не совпал" in brief_error(
        tmp_path, ledger_path, lambda d: d.update(ledger_hash="0" * 64)
    )


@pytest.mark.parametrize("reason", ["wontfix", "duplicate", "invalid", ""])
def test_brief_invalid_excluded_reason(
    tmp_path: Path, ledger_path: tuple[Path, str], reason: str
) -> None:
    def mutate(data: Json) -> None:
        data["excluded"] = [{"source_finding": "F-003", "evidence": "x", "reason": reason}]

    assert f"недопустимая причина {reason!r}" in brief_error(tmp_path, ledger_path, mutate)


def test_brief_duplicate_of_missing_target(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    def mutate(data: Json) -> None:
        data["excluded"] = [
            {"source_finding": "F-003", "evidence": "x", "reason": "duplicate_of:F-099"}
        ]

    assert "несуществующую F-099" in brief_error(tmp_path, ledger_path, mutate)


def test_brief_duplicate_of_itself(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    def mutate(data: Json) -> None:
        data["excluded"] = [
            {"source_finding": "F-003", "evidence": "x", "reason": "duplicate_of:F-003"}
        ]

    assert "не может быть дублем самой себя" in brief_error(tmp_path, ledger_path, mutate)


def test_brief_duplicate_of_cycle(tmp_path: Path) -> None:
    rows = [
        gp.LedgerRow("F-001", "MINOR", "judge-1", "a.py:1", "а", "AGREED", "D1:agree-3/3"),
        gp.LedgerRow("F-002", "MINOR", "judge-2", "a.py:2", "б", "AGREED", "D1:agree-3/3"),
    ]
    ledger = tmp_path / "ledger.tsv"
    sha = write_ledger(ledger, rows)
    data = brief_json(sha)
    data.update(
        instructions=[],
        non_blocking_followups=[],
        excluded=[
            {"source_finding": "F-001", "evidence": "x", "reason": "duplicate_of:F-002"},
            {"source_finding": "F-002", "evidence": "x", "reason": "duplicate_of:F-001"},
        ],
        findings_total=2,
        source_findings=["F-001", "F-002"],
        terminal_objections=[{"judge": "judge-1", "evidence": "a.py:1", "defect": "возражение"}],
    )
    assert "цикл duplicate_of" in errors_text(check_brief(tmp_path, data, ledger))


def test_brief_valid_duplicate_of_existing_finding(tmp_path: Path) -> None:
    rows = [
        gp.LedgerRow("F-001", "IMPORTANT", "judge-1", "a.py:1", "а", "AGREED", "D2:agree-3/3"),
        gp.LedgerRow("F-002", "IMPORTANT", "judge-2", "a.py:1", "дубль", "AGREED", "D2:agree-3/3"),
    ]
    ledger = tmp_path / "ledger.tsv"
    sha = write_ledger(ledger, rows)
    data = brief_json(sha)
    data.update(
        non_blocking_followups=[],
        excluded=[{"source_finding": "F-002", "evidence": "x", "reason": "duplicate_of:F-001"}],
        findings_total=2,
        source_findings=["F-001", "F-002"],
    )
    assert check_brief(tmp_path, data, ledger) == []


def test_brief_withdrawn_needs_invalid_after_recheck(
    tmp_path: Path, ledger_path: tuple[Path, str]
) -> None:
    def mutate(data: Json) -> None:
        data["excluded"] = [{"source_finding": "F-003", "evidence": "x", "reason": "out_of_scope"}]

    assert "WITHDRAWN исключается с причиной invalid_after_recheck" in brief_error(
        tmp_path, ledger_path, mutate
    )


def test_brief_minor_in_instructions_and_blocking_in_followups(
    tmp_path: Path, ledger_path: tuple[Path, str]
) -> None:
    def swap(data: Json) -> None:
        instructions = copy.deepcopy(data["instructions"])
        followups = copy.deepcopy(data["non_blocking_followups"])
        assert isinstance(instructions, list)
        assert isinstance(followups, list)
        instructions[0]["source_findings"] = ["F-002"]
        followups[0]["source_findings"] = ["F-001"]
        data["instructions"], data["non_blocking_followups"] = instructions, followups

    text = brief_error(tmp_path, ledger_path, swap)
    assert "F-002: не blocking (MINOR/AGREED), но в instructions" in text
    assert "F-001: в followups допустимы только MINOR OPEN/AGREED" in text


def test_brief_empty_instructions_need_terminal_objections(tmp_path: Path) -> None:
    rows = [gp.LedgerRow("F-001", "MINOR", "judge-1", "a.py:1", "а", "AGREED", "D1:agree-3/3")]
    ledger = tmp_path / "ledger.tsv"
    sha = write_ledger(ledger, rows)
    data = brief_json(sha)
    data.update(
        instructions=[],
        non_blocking_followups=[
            {
                "id": "FU-001",
                "source_findings": ["F-001"],
                "evidence": "x",
                "action": "a",
                "acceptance": "b",
            }
        ],
        excluded=[],
        findings_total=1,
        source_findings=["F-001"],
    )
    assert "пустые instructions допустимы только при непустых terminal_objections" in errors_text(
        check_brief(tmp_path, data, ledger)
    )
    data["terminal_objections"] = [
        {"judge": "judge-2", "evidence": "app/main.py:41", "defect": "возражение C1"}
    ]
    assert check_brief(tmp_path, data, ledger) == []


DROP = object()


@pytest.mark.parametrize(
    ("key", "value", "fragment"),
    [
        ("id", "RW-1", "id должен иметь вид RW-NNN"),
        ("disposition", "advice", "disposition должен быть blocking"),
        ("criterion", 6, "criterion должен быть целым 1..5"),
        ("file", "../app.py", "выход за пределы корня"),
        ("file", "/abs/app.py", "абсолютный путь"),
        ("line_hint", None, "line_hint"),
        ("acceptance", "", "нет непустого поля acceptance"),
        ("source_findings", [], "source_findings — непустой список F-NNN"),
        ("rule_ref", DROP, "нет непустого поля rule_ref"),
    ],
)
def test_brief_invalid_instruction_fields(
    tmp_path: Path, ledger_path: tuple[Path, str], key: str, value: object, fragment: str
) -> None:
    def apply(data: Json) -> None:
        instructions = copy.deepcopy(data["instructions"])
        assert isinstance(instructions, list)
        if value is DROP:
            del instructions[0][key]
        else:
            instructions[0][key] = value
        data["instructions"] = instructions

    assert fragment in brief_error(tmp_path, ledger_path, apply)


def test_brief_duplicate_instruction_ids(tmp_path: Path) -> None:
    rows = [
        gp.LedgerRow("F-001", "IMPORTANT", "judge-1", "a.py:1", "а", "AGREED", "D1:agree-3/3"),
        gp.LedgerRow("F-002", "IMPORTANT", "judge-2", "a.py:2", "б", "AGREED", "D1:agree-3/3"),
    ]
    ledger = tmp_path / "ledger.tsv"
    sha = write_ledger(ledger, rows)
    data = brief_json(sha)
    first = copy.deepcopy(data["instructions"])
    assert isinstance(first, list)
    second = copy.deepcopy(first[0])
    assert isinstance(second, dict)
    second["source_findings"] = ["F-002"]
    data.update(
        instructions=[first[0], second],
        non_blocking_followups=[],
        excluded=[],
        findings_total=2,
        source_findings=["F-001", "F-002"],
    )
    assert "повторный id RW-001" in errors_text(check_brief(tmp_path, data, ledger))


def test_brief_root_fields_and_cycle(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    text = brief_error(
        tmp_path, ledger_path, lambda d: d.update(schema_version="2.0", cycle=1, task_id="")
    )
    assert "schema_version должен быть 1.0" in text
    assert "cycle должен быть целым 2..5" in text
    assert "нет непустой строки task_id" in text


def test_brief_terminal_objection_shape(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    text = brief_error(
        tmp_path, ledger_path, lambda d: d.update(terminal_objections=[{"judge": "judge-1"}])
    )
    assert "terminal_objections[0]" in text


def test_brief_without_ledger_checks_structure_only(
    tmp_path: Path, ledger_path: tuple[Path, str]
) -> None:
    _, sha = ledger_path
    data = brief_json(sha)
    path = write_json(tmp_path / "isolated" / "handoff" / "panel-rework-brief.json", data)
    assert vh.validate_path(path) == []
    data["excluded"] = []
    path = write_json(tmp_path / "isolated" / "handoff" / "panel-rework-brief.json", data)
    assert "F-003: потерян" in errors_text(vh.validate_path(path))


def test_brief_uses_default_ledger_of_project(kit: PanelKit) -> None:
    ledger = kit.panel / "findings-ledger.tsv"
    data = brief_json(gp.sha256_file(ledger))
    path = write_json(kit.path(BRIEF_JSON), data)
    text = errors_text(vh.validate_path(path))
    assert "не совпадает с множеством F-ID реестра" in text


def test_brief_with_missing_explicit_ledger(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    _, sha = ledger_path
    path = write_json(tmp_path / "panel-rework-brief.json", brief_json(sha))
    assert "реестр не найден" in errors_text(vh.validate_path(path, tmp_path / "нет.tsv"))


def test_brief_with_corrupt_ledger(tmp_path: Path, ledger_path: tuple[Path, str]) -> None:
    _, sha = ledger_path
    bad = tmp_path / "bad.tsv"
    bad.write_text("не реестр\n", encoding="utf-8")
    path = write_json(tmp_path / "panel-rework-brief.json", brief_json(sha))
    assert "неверный заголовок" in errors_text(vh.validate_path(path, bad))


# --------------------------------------------------------------------------- панель


def test_panel_directory_and_panel_subdirectory(kit: PanelKit) -> None:
    assert vh.validate_path(kit.team) == []
    assert vh.validate_path(kit.panel) == []


def test_panel_directory_reports_technical_status(kit: PanelKit) -> None:
    kit.replace(".ai-team/panel/d1/judge-1.md", "HAT: Реалист", "HAT: Визионер")
    errors = vh.validate_path(kit.team)
    assert errors
    assert all(e.startswith("CONSENSUS_UNAVAILABLE: ") for e in errors)


def test_agreed_reject_panel_is_structurally_valid(kit: PanelKit) -> None:
    kit.set_c1_verdicts({"judge-2": "REJECT"}, "app/main.py:41 | пример возражения")
    assert vh.validate_path(kit.team) == []


# --------------------------------------------------------------------------- CLI


def test_cli_success_prints_gate_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_json(tmp_path / "coder-01.json", coder_json())
    assert vh.main([str(path)], tmp_path) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0].startswith("УСПЕХ: ")
    assert out[-1] == "GATE: PASS"


def test_cli_error_goes_to_stderr_with_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = coder_json()
    data["changed_files"] = ["/etc/passwd"]
    path = write_json(tmp_path / "coder-01.json", data)
    assert vh.main([str(path)], tmp_path) == 1
    captured = capsys.readouterr()
    assert "ОШИБКА: " in captured.err
    assert "GATE: PASS" not in captured.out


def test_cli_checks_every_path_and_fails_if_any_invalid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = write_json(tmp_path / "good.json", coder_json())
    bad = write_json(tmp_path / "bad.json", {"task_id": "x"})
    assert vh.main([str(good), str(bad)], tmp_path) == 1
    captured = capsys.readouterr()
    assert "УСПЕХ" in captured.out
    assert "ОШИБКА" in captured.err


def test_cli_missing_file_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert vh.main([str(tmp_path / "нет.json")], tmp_path) == 1
    assert "Файл пакета не найден" in capsys.readouterr().err


def test_cli_ledger_flag(
    tmp_path: Path, ledger_path: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    ledger, sha = ledger_path
    path = write_json(tmp_path / "brief" / "panel-rework-brief.json", brief_json(sha))
    assert vh.main([str(path), "--ledger", str(ledger)], tmp_path) == 0
    assert "VALID n_instructions=1" in capsys.readouterr().out


def test_cli_usage_errors_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert vh.main(["--ledger"], tmp_path) == 2
    assert vh.main(["--unknown"], tmp_path) == 2
    assert capsys.readouterr().err.count("\n") >= 2


def test_validate_path_exports_contract_signature(tmp_path: Path) -> None:
    path = write_json(tmp_path / "coder-01.json", coder_json())
    assert vh.validate_path(str(path)) == []
    assert vh.validate_path(path, None) == []
    assert vh.unsafe_path_reason("app/main.py") is None


def test_brief_must_match_manifest_next_to_ledger(kit: PanelKit) -> None:
    ledger = kit.panel / "findings-ledger.tsv"
    manifest = json.loads(kit.read(".ai-team/panel/manifest.json"))
    data = brief_json(gp.sha256_file(ledger))
    data.update(
        source_pass_id=manifest["pass_id"],
        cycle=manifest["cycle"] + 1,
        instructions=[],
        non_blocking_followups=[
            {
                "id": "FU-001",
                "source_findings": ["F-001", "F-003", "F-004", "F-005"],
                "evidence": "d3/judge-1.md",
                "action": "Выполнить доработки уровня MINOR",
                "acceptance": "ручная сверка реестра",
            }
        ],
        excluded=[
            {
                "source_finding": "F-002",
                "evidence": "d1/judge-1.md",
                "reason": "invalid_after_recheck",
            }
        ],
        findings_total=5,
        source_findings=["F-001", "F-002", "F-003", "F-004", "F-005"],
        terminal_objections=[
            {"judge": "judge-2", "evidence": "app/main.py:41", "defect": "возражение"}
        ],
    )
    path = write_json(kit.path(BRIEF_JSON), data)
    assert vh.validate_path(path) == []
    data["source_pass_id"] = "pass-чужой"
    data["cycle"] = manifest["cycle"] + 2
    text = errors_text(vh.validate_path(write_json(path, data)))
    assert "source_pass_id не совпал с pass_id паспорта" in text
    assert "cycle должен быть циклом прохода + 1 (2)" in text
