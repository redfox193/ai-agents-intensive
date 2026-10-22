"""Контрактные тесты `scripts/orchestrate_pipeline.py` (запуск: `uv run pytest scripts -q`)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import orchestrate_pipeline as op  # noqa: E402  # путь скриптов добавлен строкой выше

SHA = "a" * 64
DIGEST = "c" * 64
INFO = op.PassInfo("LINK-42-c1-1", 1, SHA)
FINAL_INFO = op.PassInfo("LINK-42-c1-1", 1, SHA, DIGEST, "ACCEPT")
HAS_REFERENCE = (PROJECT_ROOT / op.MANIFEST_JSON).is_file()
needs_reference = pytest.mark.skipif(
    not HAS_REFERENCE, reason="эталонные фикстуры .ai-team/panel ещё не собраны"
)


# --------------------------------------------------------------------------------------
# Чистые функции: модель, команды, брифы
# --------------------------------------------------------------------------------------


def write_opencode_config(path: Path, model: object = None, small: object = None) -> Path:
    """opencode.json во временном каталоге; `None` — каноническая модель."""
    data = {"model": model or op.DEFAULT_MODEL, "small_model": small or op.DEFAULT_MODEL}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_resolve_model_accepts_only_canonical_model(tmp_path: Path) -> None:
    """RW-004: канонической считается только `opencode/deepseek-v4.1-flash-free`."""
    config = write_opencode_config(tmp_path / "opencode.json")
    canonical = op.DEFAULT_MODEL
    assert canonical == "opencode/deepseek-v4.1-flash-free"
    assert op.resolve_model(None, {}, config) == canonical
    assert op.resolve_model(canonical, {op.MODEL_ENV: canonical}, config) == canonical
    assert op.resolve_model(None, {op.MODEL_ENV: ""}, config) == canonical
    assert op.resolve_model(None, {}) == canonical  # настоящий opencode.json проекта


def test_resolve_model_rejects_foreign_cli_and_env_models(tmp_path: Path) -> None:
    config = write_opencode_config(tmp_path / "opencode.json")
    with pytest.raises(ValueError, match="opencode/deepseek-v4.1-flash-free"):
        op.resolve_model("opencode/deepseek-v4.1-cli", {}, config)
    with pytest.raises(ValueError, match="не допускается"):
        op.resolve_model(None, {op.MODEL_ENV: "opencode/deepseek-v4.1-env"}, config)


@pytest.mark.parametrize("field", ["model", "small_model"])
def test_resolve_model_checks_opencode_json_fields(tmp_path: Path, field: str) -> None:
    foreign = {field: "agentplatform/z-ai/glm-5.2"}
    config = write_opencode_config(tmp_path / "opencode.json", **_config_args(foreign))
    with pytest.raises(ValueError, match=field):
        op.resolve_model(None, {}, config)


def _config_args(fields: dict[str, str]) -> dict[str, str]:
    """Аргументы `write_opencode_config` по имени поля opencode.json."""
    return {("small" if key == "small_model" else key): value for key, value in fields.items()}


def test_resolve_model_rejects_missing_or_broken_config(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="не читается"):
        op.resolve_model(None, {}, tmp_path / "нет.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{не json", encoding="utf-8")
    with pytest.raises(ValueError, match="не читается"):
        op.resolve_model(None, {}, broken)
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"model": op.DEFAULT_MODEL}), encoding="utf-8")
    with pytest.raises(ValueError, match="small_model"):
        op.resolve_model(None, {}, partial)


def test_foreign_model_on_command_line_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(op.MODEL_ENV, raising=False)
    with pytest.raises(SystemExit) as caught:
        op.main(["--live", "--dry-run", "--model", "opencode/deepseek-v4.1-x"])
    assert caught.value.code == 2
    assert "не допускается" in capsys.readouterr().err


def test_opencode_command_is_fresh_process_without_session_flags() -> None:
    """Команда — `opencode run -m <модель> --format json <бриф>`: без `--continue`/`--session`."""
    argv = op.build_opencode_command("opencode/deepseek-v4.1-flash-free", "бриф")
    assert argv == [
        "opencode",
        "run",
        "-m",
        "opencode/deepseek-v4.1-flash-free",
        "--format",
        "json",
        "бриф",
    ]
    assert not {"--continue", "--session", "-c", "-s"} & set(argv)


@pytest.mark.parametrize(
    ("round_id", "expected"),
    [
        ("R1", ("Скептик", "Реалист", "Визионер")),
        ("D1", ("Реалист", "Визионер", "Скептик")),
        ("D2", ("Визионер", "Скептик", "Реалист")),
        ("D3", ("Скептик", "Реалист", "Визионер")),
        ("C1", ("Общая", "Общая", "Общая")),
    ],
)
def test_hat_rotation_table(round_id: str, expected: tuple[str, str, str]) -> None:
    """Ротация шляп совпадает с таблицей контракта."""
    assert tuple(op.hat_for(round_id, seat) for seat in op.SEATS) == expected


def test_hats_match_generate_proof_rotation() -> None:
    """Таблица шляп оркестратора совпадает с ротацией проверяющего скрипта."""
    import generate_proof

    for round_id, hats in generate_proof.ROTATION.items():
        assert {seat: op.hat_for(round_id, seat) for seat in op.SEATS} == hats


def test_judge_brief_has_exact_header_and_skill_reference() -> None:
    """Бриф судьи: ссылка на скилл панели, заголовок из пяти строк, режим read-only."""
    brief = op.build_judge_brief("D1", "judge-2", INFO, "### ledger")
    assert op.PANEL_SKILL in brief
    assert op.CONSENSUS_DOC in brief
    assert "STRICT READ-ONLY" in brief
    header = f"SEAT: judge-2\nROUND: D1\nHAT: Визионер\nPROCEDURE_ACCEPTED: {SHA}\nORIGIN: live"
    assert header in brief
    assert "## Ответы на вопросы коллег" in brief
    assert "## Вопросы коллегам (к следующему раунду)" in brief
    assert "в D3" not in brief
    assert "Проход LINK-42-c1-1, задача LINK-42, цикл 1." in brief


def test_final_round_brief_is_blind_and_signs_digest() -> None:
    """C1: судья подписывает digest и не читает чужих файлов."""
    brief = op.build_judge_brief("C1", "judge-3", FINAL_INFO, "### freeze")
    assert f"FREEZE_SHA256: {DIGEST}" in brief
    assert "HAT: Общая" in brief
    assert "FALLBACK_CONSENT: YES" in brief
    assert "Кандидат: ACCEPT" in brief


def test_coder_brief_switches_skill_by_cycle() -> None:
    """Цикл 1 — `feature`, Циклы 2..5 — `rework` с брифом доработки."""
    first = op.build_coder_brief(1)
    assert op.FEATURE_SKILL in first
    assert op.REWORK_SKILL not in first
    again = op.build_coder_brief(3, op.REWORK_BRIEF)
    assert op.REWORK_SKILL in again
    assert op.REWORK_BRIEF in again
    assert "handoff/coder-03.json" in again


def test_briefs_have_no_forbidden_markers() -> None:
    """В брифах нет путей машины автора и имён лишних ролей."""
    texts = [
        op.build_coder_brief(2, op.REWORK_BRIEF),
        op.build_rework_brief_prompt(INFO, 2, SHA, "### ledger"),
    ]
    for round_id in (*op.DEBATE_ROUNDS, op.FINAL_ROUND):
        texts += [op.build_judge_brief(round_id, seat, FINAL_INFO) for seat in op.SEATS]
    pieces = (("/Us", "ers/"), ("/t", "mp/"), ("~", "/"), ("claude", " -p"), ("codex", " exec"))
    pieces += (("re", "viewer"), ("arch", "itect"), ("ana", "lyst"), ("expl", "orer"))
    forbidden = tuple("".join(parts) for parts in pieces)
    for text in texts:
        assert not [marker for marker in forbidden if marker in text.lower()]


def test_open_ids_and_round_context(tmp_path: Path) -> None:
    """Реестр даёт открытые F-ID; контекст D-раунда содержит реестр и ответы прошлого раунда."""
    header = "f_id\tseverity\tjudge\tlocation\tsummary\tstatus\tresolution\n"
    rows = "F-001\tMINOR\tjudge-1\ta.py:1\tx\tOPEN\tD3:unresolved\n"
    rows += "F-002\tMINOR\tjudge-1\ta.py:2\ty\tAGREED\tD1:agree-3/3\n"
    assert op.open_finding_ids(header + rows) == ["F-001"]
    assert op.open_finding_ids(header) == []
    ledger = tmp_path / op.LEDGER_TSV
    ledger.parent.mkdir(parents=True)
    ledger.write_text(header + rows, encoding="utf-8")
    (tmp_path / op.seat_file("R1", "judge-1")).parent.mkdir(parents=True)
    (tmp_path / op.seat_file("R1", "judge-1")).write_text("SEAT: judge-1\n", encoding="utf-8")
    context = op.round_context(tmp_path, "D1")
    assert "### .ai-team/panel/r1/judge-1.md\nSEAT: judge-1" in context
    assert "### .ai-team/panel/r1/judge-2.md\n(файла нет)" in context
    brief = op.build_judge_brief("D1", "judge-1", INFO, context)
    assert "Открытые находки, по которым нужна позиция: F-001." in brief
    final = op.round_context(tmp_path, "C1")
    assert "freeze.json" in final


def test_cycle_plan_has_coder_plus_fifteen_panel_calls() -> None:
    """Один цикл: Кодер и 15 вызовов панели (3 R1 + 9 D + 3 C1)."""
    calls = op.plan_cycle_calls(1, op.DEFAULT_MODEL)
    assert len(calls) == 16
    assert all(call.argv[:3] == ["opencode", "run", "-m"] for call in calls)
    assert (
        sum("D1" in call.label or "D2" in call.label or "D3" in call.label for call in calls) == 9
    )


# --------------------------------------------------------------------------------------
# Разбор вывода
# --------------------------------------------------------------------------------------


def test_extract_text_joins_json_events() -> None:
    """Поток JSON-событий склеивается в текст; обычный текст остаётся как есть."""
    events = [
        {"type": "step_start"},
        {"type": "text", "part": {"text": "SEAT: judge-1"}},
        {"type": "text", "part": {"text": "ROUND: R1"}},
    ]
    raw = "\n".join(json.dumps(event) for event in events)
    assert op.extract_text(raw) == "SEAT: judge-1\nROUND: R1"
    assert op.extract_text("SEAT: judge-1\nROUND: R1\n") == "SEAT: judge-1\nROUND: R1"
    assert op.extract_text('{"schema_version": "1.0"}') == '{"schema_version": "1.0"}'
    assert op.extract_text("") == ""


def test_extract_text_session_error_makes_answer_unusable() -> None:
    """Событие `error` уровня сессии — ответ непригоден."""
    raw = json.dumps({"type": "text", "part": {"text": "x"}}) + "\n" + json.dumps({"type": "error"})
    assert op.extract_text(raw) == ""


def test_trim_to_header_drops_preamble_and_fence() -> None:
    """Файл судьи начинается с `SEAT:`; вступление и закрывающий блок отбрасываются."""
    text = "Вот мой ответ:\n```\nSEAT: judge-1\nROUND: R1\nFINDINGS: none\n```"
    assert op.trim_to_header(text) == "SEAT: judge-1\nROUND: R1\nFINDINGS: none"


def test_find_last_json_object_and_verdict_parsing() -> None:
    """Последний JSON-объект в тексте и вердикт из последней строки."""
    assert op.find_last_json_object('текст {"a": 1} ещё {"b": 2} конец') == {"b": 2}
    assert op.find_last_json_object("нет json") is None
    assert op.parse_verdict("GATE: PASS\nVERDICT: READY\n") == "READY"
    assert op.parse_verdict("Traceback\nValueError") is None
    assert op.last_hex(f"digest {DIGEST}\n") == DIGEST


# --------------------------------------------------------------------------------------
# Процессы: stdin закрыт, dry-run ничего не запускает
# --------------------------------------------------------------------------------------


def test_runner_closes_stdin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Каждый процесс запускается с `stdin=DEVNULL`, без shell."""
    seen: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = op.make_runner(tmp_path)(["opencode", "run", "-m", "m", "бриф"])
    assert result.returncode == 0
    assert seen["stdin"] is subprocess.DEVNULL
    assert seen.get("shell") in (None, False)


def test_dry_run_prints_commands_and_starts_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--live --dry-run` печатает команды и не создаёт ни одного процесса."""

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("dry-run не должен запускать процессы")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.delenv(op.MODEL_ENV, raising=False)
    assert op.main(["--live", "--dry-run"]) == 0
    lines = [
        line.strip()
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("opencode run")
    ]
    assert len(lines) == 18  # Кодер + 15 вызовов панели + суммаризация + Кодер rework
    assert all("-m opencode/deepseek-v4.1-flash-free" in line for line in lines)
    assert all("--continue" not in line and "--session" not in line for line in lines)


def test_dry_run_requires_live_and_cycles_are_bounded() -> None:
    """`--dry-run` без `--live` и `--max-cycles` вне 1..5 — неверное использование (код 2)."""
    for argv in (["--dry-run"], ["--live", "--max-cycles", "6"], ["--max-cycles", "0"]):
        with pytest.raises(SystemExit) as caught:
            op.main(argv)
        assert caught.value.code == 2


def test_model_flag_and_json_format_reach_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    """Каноническая `--model` и `--format json` попадают в каждую команду."""
    assert op.main(["--live", "--dry-run", "--model", op.DEFAULT_MODEL, "--max-cycles", "1"]) == 0
    lines = [
        line.strip()
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("opencode run")
    ]
    assert lines
    assert all(f"-m {op.DEFAULT_MODEL} --format json" in line for line in lines)


# --------------------------------------------------------------------------------------
# Живой цикл на заглушках процессов
# --------------------------------------------------------------------------------------


class FakeWorld:
    """Заглушка внешнего мира: ответы судей и помощников задаются сценарием."""

    def __init__(self, root: Path, verdicts: Sequence[str]) -> None:
        self.root = root
        self.verdicts = list(verdicts)
        self.calls: list[list[str]] = []
        self.opencode_calls: list[list[str]] = []
        self.judge_failures: set[str] = set()
        self.summarizer_text: str | None = None
        self.verify_count = 0
        self.on_judge: Callable[[], None] | None = None

    def runner(self, argv: Sequence[str]) -> op.RunResult:
        args = list(argv)
        self.calls.append(args)
        if args[0] == "git":
            return op.RunResult(0, "diff --git a/app/x.py b/app/x.py\n", "")
        if args[0] == "opencode":
            self.opencode_calls.append(args)
            return self._opencode(args)
        script = Path(args[1]).name
        assert script == "generate_proof.py"
        sub = args[2] if len(args) > 2 else ""
        if sub in {"manifest", "ledger", "freeze"}:
            return op.RunResult(0, f"{SHA}\n", "")
        verdict = self.verdicts[min(self.verify_count, len(self.verdicts) - 1)]
        self.verify_count += 1
        code = op.VERDICT_EXIT[verdict]
        return op.RunResult(code, f"GATE: X. причина\nVERDICT: {verdict}\n", "")

    def _opencode(self, args: list[str]) -> op.RunResult:
        brief = args[-1]
        if brief.startswith("Ты Кодер"):
            self._write_coder_files(brief)
            return op.RunResult(0, "готово", "")
        if "panel-rework-summarizer" in brief.splitlines()[0]:
            assert f"### diff ({op.DIFF_COMMAND})\ndiff --git" in brief
            assert "ledger_hash" in brief
            text = self.summarizer_text or json.dumps({"instructions": [{"id": "RW-001"}]})
            return op.RunResult(0, text, "")
        first = brief.splitlines()[0]
        seat = first.split()[1]
        round_id = first.split("раунд ")[1].split(",")[0]
        if self.on_judge is not None:
            self.on_judge()
        if f"{round_id}-{seat}" in self.judge_failures:
            return op.RunResult(1, "", "транспортный сбой")
        return op.RunResult(0, f"Вступление\nSEAT: {seat}\nROUND: {round_id}\nFINDINGS: none", "")

    def _write_coder_files(self, brief: str) -> None:
        number = brief.split("handoff/coder-")[1][:2]
        (self.root / "handoff").mkdir(parents=True, exist_ok=True)
        (self.root / f"handoff/coder-{number}.json").write_text("{}", encoding="utf-8")
        (self.root / op.HANDOFF_MD).parent.mkdir(parents=True, exist_ok=True)
        (self.root / op.HANDOFF_MD).write_text("# Handoff\n", encoding="utf-8")


def make_context(
    world: FakeWorld,
    max_cycles: int = 5,
    code_gate: list[list[op.GateResult]] | None = None,
    validate_errors: list[str] | None = None,
) -> op.LiveContext:
    """Живой контекст с заглушками; `code_gate` — список ответов по циклам (пусто = зелёный)."""
    queue = list(code_gate or [])

    def gate(root: Path, cycle: int, journal: op.Journal) -> list[op.GateResult]:
        return queue.pop(0) if queue else []

    def validate(path: Path) -> list[str]:
        return list(validate_errors) if validate_errors and "brief" in path.name else []

    deps = op.LiveDeps(runner=world.runner, validate=validate, code_gate=gate)
    journal = op.Journal(world.root / op.LOG_RELATIVE)
    return op.LiveContext(world.root, op.DEFAULT_MODEL, max_cycles, journal, deps)


def judge_calls(world: FakeWorld) -> list[list[str]]:
    return [call for call in world.opencode_calls if call[-1].startswith("Ты judge-")]


def test_live_accept_in_first_cycle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """ACCEPT: один Кодер, ровно 15 вызовов судей, суммаризации нет, код 0."""
    world = FakeWorld(tmp_path, ["READY"])
    assert op.run_live(make_context(world)) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "VERDICT: READY"
    assert len(judge_calls(world)) == 15
    assert len(world.opencode_calls) == 16
    saved = (tmp_path / op.seat_file("R1", "judge-2")).read_text(encoding="utf-8")
    assert saved.startswith("SEAT: judge-2\nROUND: R1")
    for call in world.opencode_calls:
        assert call[:3] == ["opencode", "run", "-m"]
        assert "--continue" not in call
        assert "--session" not in call
    assert (tmp_path / op.seat_file("C1", "judge-1")).is_file()


def test_live_reject_calls_summarizer_and_feeds_rework(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """REJECT → суммаризатор → бриф сохранён → второй Кодер в режиме `rework` → READY."""
    world = FakeWorld(tmp_path, ["REJECT", "READY"])
    assert op.run_live(make_context(world)) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "VERDICT: READY"
    summarizers = [c for c in world.opencode_calls if "panel-rework-summarizer" in c[-1]]
    assert len(summarizers) == 1
    assert (tmp_path / op.REWORK_BRIEF).is_file()
    coders = [c for c in world.opencode_calls if c[-1].startswith("Ты Кодер")]
    assert len(coders) == 2
    assert op.REWORK_SKILL in coders[1][-1]
    assert op.REWORK_BRIEF in coders[1][-1]
    assert len(judge_calls(world)) == 30


def test_live_cycle_ceiling_is_escalate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """После пятого REJECT шестого Кодера нет: ESCALATE (код 2)."""
    world = FakeWorld(tmp_path, ["REJECT"])
    assert op.run_live(make_context(world)) == 2
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1] == "VERDICT: ESCALATE"
    coders = [c for c in world.opencode_calls if c[-1].startswith("Ты Кодер")]
    summarizers = [c for c in world.opencode_calls if "panel-rework-summarizer" in c[-1]]
    assert len(coders) == 5
    assert len(summarizers) == 4
    assert len(judge_calls(world)) == 75


def test_live_red_code_gate_never_ready_and_skips_panel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Красный CODE_GATE возвращает Кодера, панель не запускается, READY невозможен."""
    red = [op.GateResult("uv run pytest -q", 1, "1 failed")]
    world = FakeWorld(tmp_path, ["READY"])
    context = make_context(world, max_cycles=2, code_gate=[red, red])
    assert op.run_live(context) == 2
    assert capsys.readouterr().out.strip().splitlines()[-1] == "VERDICT: ESCALATE"
    assert judge_calls(world) == []
    brief = json.loads((tmp_path / op.GATE_FAILURE_BRIEF).read_text(encoding="utf-8"))
    assert brief["failures"][0]["id"] == "CG-001"
    second_coder = [c for c in world.opencode_calls if c[-1].startswith("Ты Кодер")][1]
    assert op.GATE_FAILURE_BRIEF in second_coder[-1]


def test_live_missing_judge_is_quorum_escalate_with_one_retry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Судья без ответа: один повтор, исходная попытка сохранена, затем ESCALATE."""
    world = FakeWorld(tmp_path, ["ESCALATE"])
    world.judge_failures = {"R1-judge-3"}
    assert op.run_live(make_context(world)) == 2
    assert capsys.readouterr().out.strip().splitlines()[-1] == "VERDICT: ESCALATE"
    attempts = [
        c for c in judge_calls(world) if c[-1].startswith("Ты judge-3 Панели техлидов, раунд R1,")
    ]
    assert len(attempts) == 2
    kept = list((tmp_path / "handoff" / "attempts").glob("R1-judge-3.attempt*.txt"))
    assert len(kept) == 2
    assert not (tmp_path / op.seat_file("R1", "judge-3")).exists()
    assert not [c for c in judge_calls(world) if "раунд D1" in c[-1]]


def test_live_summarizer_ask_or_invalid_brief_escalates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`ASK:` суммаризатора и бриф, не прошедший валидацию, дают ESCALATE."""
    world = FakeWorld(tmp_path, ["REJECT"])
    world.summarizer_text = "ASK: diff"
    assert op.run_live(make_context(world)) == 2
    assert "ASK: diff" in (tmp_path / op.LOG_RELATIVE).read_text(encoding="utf-8")
    capsys.readouterr()

    other = tmp_path / "second"
    other.mkdir()
    world2 = FakeWorld(other, ["REJECT"])
    context = make_context(world2, validate_errors=["нет source_findings"])
    assert op.run_live(context) == 2
    summarizers = [c for c in world2.opencode_calls if "panel-rework-summarizer" in c[-1]]
    assert len(summarizers) == 2


def test_live_archives_previous_panel(tmp_path: Path) -> None:
    """Файлы прошлого прохода уходят в архив, новый проход начинается с чистого каталога."""
    old = tmp_path / op.seat_file("R1", "judge-1")
    old.parent.mkdir(parents=True)
    old.write_text("старый", encoding="utf-8")
    world = FakeWorld(tmp_path, ["READY"])
    assert op.run_live(make_context(world)) == 0
    assert "Вступление" not in old.read_text(encoding="utf-8")
    assert old.read_text(encoding="utf-8").startswith("SEAT: judge-1")
    archived = list((tmp_path / "handoff" / "panel-archive").rglob("judge-1.md"))
    assert [path.read_text(encoding="utf-8") for path in archived] == ["старый"]


def test_judge_brief_and_summarizer_diff_are_limited_to_product_paths(tmp_path: Path) -> None:
    """RW-003: дифф для судей и суммаризатора — только `app/`, `tests/`, `alembic/`."""
    assert op.DIFF_COMMAND == "git diff main...HEAD -- app tests alembic"
    assert op.DIFF_COMMAND in op.build_judge_brief("R1", "judge-1", INFO)
    world = FakeWorld(tmp_path, ["REJECT", "READY"])
    assert op.run_live(make_context(world)) == 0
    diffs = [call for call in world.calls if call[:2] == ["git", "diff"]]
    assert diffs
    assert all(
        call == ["git", "diff", "main...HEAD", "--", "app", "tests", "alembic"] for call in diffs
    )


def seed_protected_tree(root: Path) -> None:
    """Дерево с защищёнными файлами, продуктом и спекой с реальным списком Blast Radius."""
    files = {
        "AGENTS.md": "правила\n",
        ".agents/AGENTS.md": "правила агентов\n",
        "pyproject.toml": "[project]\n",
        "uv.lock": "lock\n",
        ".agents/skills/onboard/SKILL.md": "onboard\n",
        "app/main.py": "A = 1\n",
        "app/db/session.py": "S = 1\n",
        "tests/flat_api/test_link_toggle.py": "T = 1\n",
        "alembic/versions/0001_init.py": "M = 1\n",
    }
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    spec = root / op.SPEC
    spec.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / op.SPEC, spec)


def git(root: Path, *args: str) -> None:
    """Команда git во временном репозитории (без подписи и глобальных настроек)."""
    config = ["-c", "user.name=t", "-c", "user.email=t@example.org", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", *config, *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Чистый git-репозиторий с веткой main; эталонные sha256 защищённых файлов — из сида."""
    root = tmp_path / "repo"
    root.mkdir()
    seed_protected_tree(root)
    pins = {
        name: op.sha256_of(root / name) if (root / name).is_file() else None
        for name in op.PROTECTED_FILE_SHA256
    }
    monkeypatch.setattr(op, "PROTECTED_FILE_SHA256", pins)
    git(root, "init", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-m", "base")
    return root


def test_allowed_paths_come_from_spec_blast_radius() -> None:
    allowed = op.allowed_paths(PROJECT_ROOT)
    assert "app/services/link.py" in allowed
    assert "alembic/versions/" in allowed
    assert "tests/flat_api/test_link_toggle.py" in allowed
    assert "app/db/session.py" not in allowed
    assert "tests/flat_api/test_characterization.py" not in allowed


def test_blast_radius_is_clean_for_untouched_tree(repo: Path) -> None:
    assert op.check_blast_radius(repo) == []


def test_blast_radius_allows_declared_product_changes(repo: Path) -> None:
    (repo / "app/main.py").write_text("A = 2\n", encoding="utf-8")
    (repo / "alembic/versions/0002_clicks.py").write_text("M = 2\n", encoding="utf-8")
    assert op.check_blast_radius(repo) == []


@pytest.mark.parametrize(
    "relative",
    [
        "AGENTS.md",
        ".agents/AGENTS.md",
        "pyproject.toml",
        "uv.lock",
        op.SPEC,
        ".agents/skills/onboard/SKILL.md",
    ],
)
def test_blast_radius_rejects_changed_protected_file(repo: Path, relative: str) -> None:
    with (repo / relative).open("a", encoding="utf-8") as handle:
        handle.write("несанкционированная правка\n")
    assert op.check_blast_radius(repo) == [f"защищённый файл изменён: {relative}"]


def test_blast_radius_rejects_deleted_protected_file(repo: Path) -> None:
    (repo / "uv.lock").unlink()
    assert op.check_blast_radius(repo) == ["защищённый файл изменён: uv.lock"]


def test_blast_radius_rejects_product_file_outside_allowed_list(repo: Path) -> None:
    (repo / "app/db/session.py").write_text("S = 2\n", encoding="utf-8")
    (repo / "app/новый.py").write_text("N = 1\n", encoding="utf-8")
    assert op.check_blast_radius(repo) == [
        "файл вне разрешённого списка спеки: app/db/session.py",
        "файл вне разрешённого списка спеки: app/новый.py",
    ]


def test_blast_radius_sees_commits_made_on_branch(repo: Path) -> None:
    git(repo, "checkout", "-b", "feature/LINK-42-enable-link")
    (repo / "app/db/session.py").write_text("S = 3\n", encoding="utf-8")
    git(repo, "commit", "-am", "правка вне списка")
    assert op.check_blast_radius(repo) == ["файл вне разрешённого списка спеки: app/db/session.py"]


@pytest.mark.parametrize(
    "relative",
    ["AGENTS.md", "uv.lock", op.SPEC, ".agents/skills/specify/SKILL.md"],
)
def test_blast_radius_rejects_committed_protected_change(repo: Path, relative: str) -> None:
    """RW-201: закоммиченная правка (или создание) защищённого файла ловится по sha256."""
    git(repo, "checkout", "-b", "feature/LINK-42-enable-link")
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write("закоммиченная подмена\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "подмена защищённого файла")
    assert op.changed_paths(repo, op.PROTECTED_FILES, vs_base=False) == set()
    errors = op.check_blast_radius(repo)
    assert f"защищённый файл изменён: {relative}" in errors


def test_blast_radius_fails_closed_when_base_diff_fails(repo: Path) -> None:
    """RW-201: `git diff main...HEAD` с кодом 128 не превращается в пустой список."""
    git(repo, "branch", "-m", "main", "trunk")
    assert op.changed_paths(repo, op.PRODUCT_PATHS, vs_base=True) is None
    assert op.changed_paths(repo, op.PRODUCT_PATHS, vs_base=False) == set()
    assert op.check_blast_radius(repo) == [
        "не удалось определить изменения относительно базовой ветки (fail-closed)"
    ]


def test_protected_pins_match_project_files() -> None:
    """RW-201: эталонные sha256 совпадают с файлами проекта; скиллов Дня 1 в ветке нет."""
    assert op.PROTECTED_FILES == tuple(op.PROTECTED_FILE_SHA256)
    assert op.SPEC in op.PROTECTED_FILE_SHA256
    assert op._protected_hash_mismatches(PROJECT_ROOT) == set()  # pyright: ignore[reportPrivateUsage]


def test_blast_radius_fails_closed_without_git_or_allowed_list(tmp_path: Path, repo: Path) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    seed_protected_tree(bare)
    assert op.check_blast_radius(bare) == ["git недоступен: Blast Radius проверить нельзя"]
    (repo / op.SPEC).write_text("# спека без списка\n", encoding="utf-8")
    assert op.check_blast_radius(repo)[0].endswith(
        "нет списка разрешённых файлов в разделе Blast Radius"
    )
    (repo / op.SPEC).unlink()
    assert "не читается" in op.check_blast_radius(repo)[0]


def test_blast_radius_is_a_required_code_gate_step() -> None:
    """RW-003: шаг есть в `gate_steps()` и обязателен для свидетельства CODE_GATE."""
    steps = {step.label: step for step in op.gate_steps()}
    step = steps[op.BLAST_STEP_LABEL]
    assert step.argv[-2:] == ("scripts/orchestrate_pipeline.py", "--check-blast-radius")
    assert not step.needs_db
    assert "check-blast-radius" in op.GATE_REQUIRED
    errors = op.gate_errors_in_commands([{"cmd": "uv run pytest -q", "exit_code": 0}])
    assert "нет обязательной команды `check-blast-radius`" in errors


def test_check_blast_radius_cli_reports_and_sets_exit_code(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(op, "ROOT", repo)
    assert op.main(["--check-blast-radius"]) == 0
    assert capsys.readouterr().out.strip() == "BLAST RADIUS: OK"
    (repo / "AGENTS.md").write_text("взлом\n", encoding="utf-8")
    assert op.main(["--check-blast-radius"]) == 1
    out = capsys.readouterr().out
    assert "BLAST RADIUS: защищённый файл изменён: AGENTS.md" in out
    assert out.strip().endswith("нарушения найдены")


def test_tree_fingerprint_covers_whole_tree_and_skips_caches(repo: Path) -> None:
    """RW-202: отпечаток видит правки, добавления и удаления везде, но не кэши и `.ai-team/`."""
    (repo / "scripts").mkdir()
    (repo / "scripts/tool.py").write_text("X = 1\n", encoding="utf-8")
    base = op.tree_fingerprint(repo)
    assert {"app/main.py", "AGENTS.md", "uv.lock", op.SPEC, "scripts/tool.py"} <= set(base)
    for ignored in (
        "app/__pycache__/main.cpython-314.pyc",
        "app/stale.pyc",
        ".ai-team/panel/r1/x.md",
        "handoff/a.txt",
        ".git/refs/x",
        ".venv/lib/x.py",
        ".pytest_cache/x",
        ".ruff_cache/x",
        ".mypy_cache/x",
    ):
        (repo / ignored).parent.mkdir(parents=True, exist_ok=True)
        (repo / ignored).write_text("шум\n", encoding="utf-8")
    assert op.tree_fingerprint(repo) == base
    (repo / "app/handoff").mkdir()
    (repo / "app/handoff/x.txt").write_text("вложенный handoff не исключение\n", encoding="utf-8")
    assert op.tree_fingerprint(repo) != base
    (repo / "app/handoff/x.txt").unlink()
    (repo / "scripts/tool.py").write_text("X = 2\n", encoding="utf-8")
    assert op.tree_fingerprint(repo) != base


JUDGE_TREE = (
    "app/main.py",
    "AGENTS.md",
    "uv.lock",
    "opencode.json",
    "specs/LINK-42-enable-link.md",
    "docs/risk-plan-LINK-42.md",
    "prompts/01-coder.md",
)


@pytest.mark.parametrize(
    "mutation",
    [
        "edit_app",
        "new_script",
        "delete_test",
        "edit_agents",
        "edit_skill",
        "edit_spec",
        "edit_risk_plan",
        "edit_opencode_json",
        "edit_uv_lock",
        "edit_prompt",
        "new_root_file",
    ],
)
def test_judge_writing_outside_ai_team_violates_read_only(tmp_path: Path, mutation: str) -> None:
    """RW-004/RW-202: запись судьи в любое место вне `.ai-team/` и `handoff/` — нарушение."""
    for relative in (
        *JUDGE_TREE,
        "tests/test_x.py",
        ".agents/skills/teamlead-panel/SKILL.md",
    ):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text("исходное\n", encoding="utf-8")

    def overwrite(relative: str) -> Callable[[], None]:
        def action() -> None:
            (tmp_path / relative).write_text("взлом\n", encoding="utf-8")

        return action

    def add_file(relative: str) -> Callable[[], None]:
        def action() -> None:
            (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / relative).write_text("1\n", encoding="utf-8")

        return action

    actions: dict[str, Callable[[], None]] = {
        "edit_app": overwrite("app/main.py"),
        "new_script": add_file("scripts/x.py"),
        "delete_test": (tmp_path / "tests/test_x.py").unlink,
        "edit_agents": overwrite("AGENTS.md"),
        "edit_skill": overwrite(".agents/skills/teamlead-panel/SKILL.md"),
        "edit_spec": overwrite("specs/LINK-42-enable-link.md"),
        "edit_risk_plan": overwrite("docs/risk-plan-LINK-42.md"),
        "edit_opencode_json": overwrite("opencode.json"),
        "edit_uv_lock": overwrite("uv.lock"),
        "edit_prompt": overwrite("prompts/01-coder.md"),
        "new_root_file": add_file("notes.txt"),
    }
    world = FakeWorld(tmp_path, ["READY"])
    world.on_judge = actions[mutation]
    with pytest.raises(op.JudgeReadOnlyViolationError, match="read-only"):
        op.run_judge(make_context(world), "R1", "judge-1", INFO, "")
    assert not (tmp_path / op.seat_file("R1", "judge-1")).exists()


def test_judge_may_not_touch_files_but_orchestrator_writes_are_allowed(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app/main.py").write_text("A = 1\n", encoding="utf-8")
    world = FakeWorld(tmp_path, ["READY"])
    assert op.run_judge(make_context(world), "R1", "judge-1", INFO, "") is True
    assert (tmp_path / op.seat_file("R1", "judge-1")).is_file()


def test_live_read_only_violation_escalates_instead_of_crashing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app/main.py").write_text("A = 1\n", encoding="utf-8")
    world = FakeWorld(tmp_path, ["READY"])

    def tamper() -> None:
        (tmp_path / "app/main.py").write_text("взлом\n", encoding="utf-8")

    world.on_judge = tamper
    assert op.run_live(make_context(world)) == 2
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "VERDICT: ESCALATE"
    assert any("нарушение read-only" in line and "app/main.py" in line for line in out)
    assert "нарушение read-only" in (tmp_path / op.LOG_RELATIVE).read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# Свидетельство CODE_GATE
# --------------------------------------------------------------------------------------


def seed_gate_inputs(root: Path) -> None:
    """Минимальные входы свидетельства."""
    for relative in (op.SPEC, op.RISK_PLAN, op.HANDOFF_MD):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"содержимое {relative}\n", encoding="utf-8")


def green_results() -> list[op.GateResult]:
    return [op.GateResult(step.label, 0) for step in op.gate_steps()]


def test_gate_steps_cover_required_commands() -> None:
    """Набор шагов содержит все обязательные команды свидетельства."""
    labels = " | ".join(step.label for step in op.gate_steps())
    for needed in op.GATE_REQUIRED:
        assert needed in labels
    assert "pytest scripts -q" in labels
    assert "ruff format --check" in labels


def test_run_gate_commands_keeps_order_and_skips_after_failed_migration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Результаты идут в порядке шагов; после падения `alembic upgrade` check не запускается."""
    ok = (sys.executable, "-c", "import sys; sys.exit(0)")
    bad = (sys.executable, "-c", "import sys; sys.exit(3)")
    steps = [
        op.GateStep(step.label, bad if step.label.endswith("upgrade head") else ok, step.needs_db)
        for step in op.gate_steps()
    ]
    monkeypatch.setattr(op, "gate_steps", lambda: steps)
    results = op.run_gate_commands(tmp_path)
    assert [item.label for item in results] == [step.label for step in steps]
    codes = {item.label: item.exit_code for item in results}
    assert codes["uv run alembic upgrade head"] == 3
    assert codes["uv run alembic check"] == 125
    assert codes["uv run python scripts/mutate_probe.py"] == 0
    assert codes["uv run ruff check ."] == 0


@needs_reference
def test_reference_code_gate_lists_exactly_the_gate_steps() -> None:
    """RW-203: свидетельство эталона перечисляет команды `gate_steps()` без пропусков и лишнего."""
    data = json.loads((PROJECT_ROOT / op.CODE_GATE_JSON).read_text(encoding="utf-8"))
    assert [item["cmd"] for item in data["commands"]] == [step.label for step in op.gate_steps()]


def test_check_code_gate_green_stale_and_red(tmp_path: Path) -> None:
    """Зелёное свидетельство проходит; смена входа — устарело; код не 0 — красное."""
    seed_gate_inputs(tmp_path)
    journal = op.Journal(tmp_path / op.LOG_RELATIVE)
    op.write_code_gate(tmp_path, green_results(), 1, journal)
    assert op.check_code_gate(tmp_path) == []

    (tmp_path / op.SPEC).write_text("другая спека\n", encoding="utf-8")
    assert any("spec" in error for error in op.check_code_gate(tmp_path))

    seed_gate_inputs(tmp_path)
    red = green_results()
    red[3] = op.GateResult(red[3].label, 1)
    op.write_code_gate(tmp_path, red, 1, journal)
    errors = op.check_code_gate(tmp_path)
    assert any("pytest -q" in error for error in errors)


def test_write_code_gate_keeps_equivalent_green_evidence(tmp_path: Path) -> None:
    """Живой зелёный прогон, равный имеющемуся по существу, файл не перезаписывает."""
    seed_gate_inputs(tmp_path)
    journal = op.Journal(tmp_path / op.LOG_RELATIVE)
    path = tmp_path / op.CODE_GATE_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    fixture = op.render_code_gate(tmp_path, green_results(), 1, "reference-fixture")
    path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before = path.read_bytes()
    op.write_code_gate(tmp_path, green_results(), 1, journal)
    assert path.read_bytes() == before


# --------------------------------------------------------------------------------------
# Быстрый режим на копии эталонного дерева
# --------------------------------------------------------------------------------------


def copy_reference(tmp_path: Path) -> Path:
    """Копия эталонного дерева без окружения и рабочих каталогов."""
    target = tmp_path / "tree"
    ignore = shutil.ignore_patterns(
        ".venv", ".git", "__pycache__", "handoff", ".ruff_cache", ".pytest_cache", "*.db"
    )
    shutil.copytree(PROJECT_ROOT, target, ignore=ignore)
    return target


def run_fast_in(tree: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    code = op.run_fast(tree, op.Journal(tree / op.LOG_RELATIVE))
    return code, capsys.readouterr().out.strip().splitlines()


@needs_reference
def test_fast_mode_accepts_reference_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Эталон: `GATE: PASS`, последняя строка `VERDICT: READY`, код 0."""
    tree = copy_reference(tmp_path)
    code, lines = run_fast_in(tree, capsys)
    assert code == 0
    assert "GATE: PASS" in lines
    assert lines[-1] == "VERDICT: READY"
    assert (tree / "handoff" / "pipeline-execution.log").is_file()


@needs_reference
def test_fast_mode_missing_artifact_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Нет обязательного артефакта — `VERDICT: FAIL (artifacts)`, код 1."""
    tree = copy_reference(tmp_path)
    (tree / "docs" / "gate-rubric.md").unlink()
    code, lines = run_fast_in(tree, capsys)
    assert code == 1
    assert lines[-1] == "VERDICT: FAIL (artifacts)"


@needs_reference
def test_fast_mode_red_or_stale_code_gate_is_not_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Красный код выхода или устаревшая привязка входов — не READY."""
    tree = copy_reference(tmp_path)
    path = tree / op.CODE_GATE_JSON
    data = json.loads(path.read_text(encoding="utf-8"))
    data["commands"][0]["exit_code"] = 1
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    code, lines = run_fast_in(tree, capsys)
    assert code == 1
    assert lines[-1] == "VERDICT: FAIL (code-gate)"

    tree2 = copy_reference(tmp_path / "stale")
    with (tree2 / op.SPEC).open("a", encoding="utf-8") as handle:
        handle.write("\nправка после приёмки\n")
    code, lines = run_fast_in(tree2, capsys)
    assert code == 1
    assert lines[-1] == "VERDICT: FAIL (code-gate)"


@needs_reference
def test_fast_mode_missing_judge_file_escalates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Нет файла судьи — технический исход: `VERDICT: ESCALATE`, код 2."""
    tree = copy_reference(tmp_path)
    (tree / op.seat_file("C1", "judge-2")).unlink()
    code, lines = run_fast_in(tree, capsys)
    assert code == 2
    assert lines[-1] == "VERDICT: ESCALATE"
