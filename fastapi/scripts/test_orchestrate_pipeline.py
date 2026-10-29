"""Тесты нейтрального оркестратора scripts/orchestrate_pipeline.py по всем путям."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import orchestrate_pipeline as op  # noqa: E402


def test_no_hardcoded_user_paths_in_source() -> None:
    """Инвариант нейтральности: в исходном коде оркестратора нет персональных путей."""
    source_file = SCRIPTS_DIR / "orchestrate_pipeline.py"
    content = source_file.read_text(encoding="utf-8")
    assert "/Users/" not in content
    assert "/home/" not in content
    assert "aazhiry1" not in content


def test_resolve_models_defaults_and_overrides(tmp_path: Path) -> None:
    """Проверка конфигурации 3 моделей OpenCode Go и переопределений."""
    cfg = op.resolve_models(None, {}, tmp_path / "absent.json")
    assert cfg.judge1_model == "opencode-go/deepseek-v4.1-flash"
    assert cfg.judge2_model == "opencode-go/glm-5.3-flash"
    assert cfg.judge3_model == "opencode-go/qwen3.8-flash"

    # Переопределение через env
    env = {
        "OPENCODE_MODEL_JUDGE1": "opencode-go/deepseek-v4.1-custom",
        "OPENCODE_MODEL_JUDGE2": "opencode-go/glm-5.3-custom",
        "OPENCODE_MODEL_JUDGE3": "opencode-go/qwen-custom",
    }
    cfg_env = op.resolve_models(None, env, tmp_path / "absent.json")
    assert cfg_env.judge1_model == "opencode-go/deepseek-v4.1-custom"
    assert cfg_env.judge2_model == "opencode-go/glm-5.3-custom"
    assert cfg_env.judge3_model == "opencode-go/qwen-custom"

    # Глобальный override через единый флаг/env
    global_env = {"OPENCODE_MODEL": "opencode-go/global-flash"}
    cfg_global = op.resolve_models(None, global_env, tmp_path / "absent.json")
    assert cfg_global.judge1_model == "opencode-go/global-flash"
    assert cfg_global.judge2_model == "opencode-go/global-flash"
    assert cfg_global.judge3_model == "opencode-go/global-flash"


def test_build_opencode_command_isolation() -> None:
    """Команда OpenCode запускает изолированный процесс без сессионных флагов."""
    cmd = op.build_opencode_command("opencode-go/glm-5.3-flash", "test prompt")
    assert cmd == [
        "opencode",
        "run",
        "-m",
        "opencode-go/glm-5.3-flash",
        "--format",
        "json",
        "test prompt",
    ]
    forbidden = {"--continue", "--session", "-c", "-s"}
    assert not (set(cmd) & forbidden)


def test_path_1_ready_when_all_judges_accept(tmp_path: Path) -> None:
    """Путь 1: ACCEPT / READY — все судьи вернули ACCEPT без блокирующих находок."""
    panel_dir = tmp_path / ".ai-team" / "panel"
    panel_dir.mkdir(parents=True)

    # 3 судьи единогласно принимают код
    for i, hat in [(1, "Скептик"), (2, "Реалист"), (3, "Визионер")]:
        judge_data = {
            "judge": f"judge-{i}",
            "hat": hat,
            "verdict": "ACCEPT",
            "findings": [
                {
                    "id": f"F-00{i}",
                    "severity": "MINOR",
                    "location": "app/api/billing.py:10",
                    "summary": "Чистый стиль",
                }
            ],
        }
        (panel_dir / f"judge-{i}.json").write_text(json.dumps(judge_data), encoding="utf-8")

    code, verdict = op.evaluate_package(tmp_path)
    assert code == op.EXIT_READY
    assert verdict == "VERDICT: READY"


def test_path_2_rework_when_judge_rejects_and_creates_brief(tmp_path: Path) -> None:
    """Путь 2: REWORK / REJECT — есть замечания, суммаризатор создаёт panel-rework-brief.json."""
    panel_dir = tmp_path / ".ai-team" / "panel"
    panel_dir.mkdir(parents=True)

    # Judge-1 (Скептик) нашёл блокер
    judge1_data = {
        "judge": "judge-1",
        "hat": "Скептик",
        "verdict": "REJECT",
        "findings": [
            {
                "id": "F-001",
                "severity": "BLOCKER",
                "location": "app/services/billing.py:45",
                "summary": "Отсутствует проверка на отрицательный баланс",
            }
        ],
    }
    (panel_dir / "judge-1.json").write_text(json.dumps(judge1_data), encoding="utf-8")

    # Judge-2 принял
    judge2_data = {"judge": "judge-2", "hat": "Реалист", "verdict": "ACCEPT", "findings": []}
    (panel_dir / "judge-2.json").write_text(json.dumps(judge2_data), encoding="utf-8")

    code, verdict = op.evaluate_package(tmp_path)
    assert code == op.EXIT_REWORK
    assert verdict == "VERDICT: REWORK"

    # Проверяем, что суммаризатор создал валидный бриф
    brief_file = tmp_path / "handoff" / "panel-rework-brief.json"
    assert brief_file.is_file()
    brief_data = json.loads(brief_file.read_text(encoding="utf-8"))
    assert brief_data["blocking_count"] == 1
    assert len(brief_data["instructions"]) == 1
    inst = brief_data["instructions"][0]
    assert inst["id"] == "RW-001"
    assert inst["severity"] == "BLOCKER"
    assert "app/services/billing.py:45" in inst["location"]


def test_path_3_gate_failure(tmp_path: Path) -> None:
    """Путь 3: GATE_FAILURE — детерминированный CODE_GATE завершился ошибкой."""
    ai_team = tmp_path / ".ai-team"
    ai_team.mkdir(parents=True)
    gate_data = {
        "status": "FAIL",
        "steps": [
            {"step": "verify_techlead_gate", "exit_code": 1, "stdout_tail": "Failed on step 3"}
        ],
    }
    (ai_team / "code-gate.json").write_text(json.dumps(gate_data), encoding="utf-8")

    code, verdict = op.evaluate_package(tmp_path)
    assert code == op.EXIT_GATE_FAILURE
    assert "GATE_FAILURE" in verdict
    assert "verify_techlead_gate" in verdict


def test_path_4_escalate_when_corrupted_or_missing_evaluations(tmp_path: Path) -> None:
    """Путь 4: ESCALATE — непредвиденное состояние (нет судей, битый файл)."""
    # Пустой каталог без артефактов
    code, verdict = op.evaluate_package(tmp_path)
    assert code == op.EXIT_ESCALATE
    assert "ESCALATE" in verdict

    # Каталог с повреждённым файлом судьи
    panel_dir = tmp_path / ".ai-team" / "panel"
    panel_dir.mkdir(parents=True)
    (panel_dir / "judge-1.json").write_text("{невалидный json", encoding="utf-8")
    code, verdict = op.evaluate_package(tmp_path)
    assert code == op.EXIT_ESCALATE
    assert "ESCALATE" in verdict


def test_main_cli_dry_run(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Проверка работы CLI флагов --live и --dry-run."""
    monkeypatch.setattr(op, "ROOT", tmp_path)
    # Создаём эталонные файлы для READY
    panel_dir = tmp_path / ".ai-team" / "panel"
    panel_dir.mkdir(parents=True)
    for i in range(1, 4):
        (panel_dir / f"judge-{i}.json").write_text(
            json.dumps({"verdict": "ACCEPT", "findings": []}), encoding="utf-8"
        )

    exit_code = op.main(["--live", "--dry-run", "--task-id", "TEST-01"])
    captured = capsys.readouterr().out
    assert exit_code == op.EXIT_READY
    assert "[DRY-RUN]" in captured
    assert "VERDICT: READY" in captured


def test_code_gate_detects_kb_sync_failure(tmp_path: Path) -> None:
    """CODE_GATE бракует задачу при сбое декларативной синхронизации базы знаний."""
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    # Скрипт проверки базы знаний завершается с ошибкой (рассинхрон)
    (tools_dir / "verify_kb_sync.py").write_text("import sys; sys.exit(1)", encoding="utf-8")
    passed, reason, res = op.run_code_gate(tmp_path)
    assert passed is False
    assert "kb_sync" in reason
    assert res["status"] == "FAIL"
