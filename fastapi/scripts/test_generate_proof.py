"""Контрактные тесты `generate_proof.py`: механика Панели техлидов на копии эталона LINK-42.

Каждый дефектный сценарий правит копию эталона в `tmp_path` и ждёт строго определённый исход
по контракту: READY, согласованный REJECT или технический ESCALATE с нужным статусом.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import generate_proof as gp
import pytest

if TYPE_CHECKING:
    from conftest import PanelKit

PANEL = ".ai-team/panel"
ALL_REJECT = {"judge-1": "REJECT", "judge-2": "REJECT", "judge-3": "REJECT"}
OBJECTION = "app/main.py:41 | пример возражения"


def fake_checks(pytest_code: int) -> Callable[[Path], dict[str, int]]:
    """Подмена живых проверок: фиксированные коды выхода без запуска ruff и pytest."""

    def checks(root: Path) -> dict[str, int]:
        assert root.is_dir()
        return {"ruff_check": 0, "pytest": pytest_code}

    return checks


def reasons_text(result: gp.PanelResult) -> str:
    """Причины исхода одной строкой для поиска подстроки."""
    return "\n".join(result.reasons)


def assert_escalate(result: gp.PanelResult, status: str, fragment: str) -> None:
    """Технический исход нужного класса с причиной, содержащей фрагмент."""
    assert result.verdict == "ESCALATE", reasons_text(result)
    assert result.technical_status == status, reasons_text(result)
    assert result.proof["verdict"] is None
    assert result.proof["technical_status"] == status
    assert fragment in reasons_text(result), reasons_text(result)


# --------------------------------------------------------------------------- happy path


def test_reference_package_is_ready(kit: PanelKit) -> None:
    result = kit.check()
    assert result.verdict == "READY", reasons_text(result)
    assert result.technical_status is None
    assert result.reasons == []
    assert result.proof["verdict"] == "ACCEPT"
    assert result.proof["candidate"] == "ACCEPT"
    assert result.proof["calls"] == 15
    assert result.proof["open_blocking"] == 0
    assert result.proof["agreed_blocking"] == 0


def test_reference_ledger_covers_all_outcomes(kit: PanelKit) -> None:
    rows = gp.build_ledger(kit.panel)
    by_id = {row.f_id: row for row in rows}
    assert list(by_id) == ["F-001", "F-002", "F-003", "F-004", "F-005"]
    assert {row.judge for row in rows} == {"judge-1", "judge-2", "judge-3"}
    assert (by_id["F-001"].severity, by_id["F-001"].status) == ("MINOR", "AGREED")
    assert by_id["F-001"].resolution == "D2:agree-3/3"
    assert by_id["F-002"].status == "WITHDRAWN"
    assert by_id["F-002"].resolution == "D1:withdrawn-by-author"
    assert by_id["F-004"].resolution == "D3:agree-3/3"
    assert by_id["F-004"].severity == "MINOR"
    assert any(row.status == "AGREED" and row.severity == "MINOR" for row in rows)
    assert not [r for r in rows if r.severity in gp.BLOCKING_SEVERITIES and r.status != "WITHDRAWN"]


def test_check_panel_does_not_write_files(kit: PanelKit) -> None:
    kit.delete(".ai-team/consensus-proof.json")
    kit.delete(".ai-team/verdict.md")
    kit.check()
    assert not (kit.team / "consensus-proof.json").exists()
    assert not (kit.team / "verdict.md").exists()


def test_reference_artifacts_are_fixed_point(kit: PanelKit) -> None:
    """Повторный verify на эталоне не меняет ни байта детерминированных файлов."""
    before = {name: kit.read(f".ai-team/{name}") for name in ("consensus-proof.json", "verdict.md")}
    assert kit.run_verify() == 0
    assert kit.run_verify() == 0
    after = {name: kit.read(f".ai-team/{name}") for name in before}
    assert after == before
    assert before["verdict.md"].startswith("Вердикт: READY\n\nVERDICT: ACCEPT\n")


def test_verify_prints_gate_pass_and_writes_gate_proof(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kit.run_verify() == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-1] == "VERDICT: READY"
    assert lines[-2].startswith("GATE: PASS. Протокол: ")
    proof = json.loads(kit.read("handoff/03-gate-proof.json"))
    assert proof["verdict"] == "ACCEPT"
    assert proof["task_id"] == "LINK-42"
    assert proof["consensus_proof_sha256"] == gp.sha256_file(kit.team / "consensus-proof.json")
    assert proof["ledger_sha256"] == gp.sha256_file(kit.panel / "findings-ledger.tsv")


def test_verdict_md_has_contract_shape(kit: PanelKit) -> None:
    kit.run_verify()
    lines = kit.read(".ai-team/verdict.md").splitlines()
    assert lines[0] == "Вердикт: READY"
    assert lines[2] == "VERDICT: ACCEPT"
    assert any(line.startswith("Run: pass_id=") for line in lines)
    assert any(line.startswith("Cycle: ") for line in lines)
    assert any(line.startswith("Artifact-SHA256: ") for line in lines)
    assert any(
        line.startswith("Consensus-Proof: .ai-team/consensus-proof.json (sha256 ") for line in lines
    )
    assert [line[:2] for line in lines if line[:3] in {f"{n}. " for n in range(1, 6)}] == [
        "1.",
        "2.",
        "3.",
        "4.",
        "5.",
    ]
    assert str(kit.root) not in "\n".join(lines)


def test_proof_has_no_timestamp_and_sorted_keys(kit: PanelKit) -> None:
    text = kit.read(".ai-team/consensus-proof.json")
    data = json.loads(text)
    assert list(data) == sorted(data)
    assert "generated_at" not in data
    assert text.endswith("}\n")


# --------------------------------------------------------------------------- кворум и файлы


def test_two_judges_instead_of_three_is_quorum_unavailable(kit: PanelKit) -> None:
    kit.delete(f"{PANEL}/c1/judge-3.md")
    assert_escalate(kit.check(), "QUORUM_UNAVAILABLE", "C1/judge-3: нет файла судьи")


def test_missing_round_directory_is_quorum_unavailable(kit: PanelKit) -> None:
    kit.delete(f"{PANEL}/d2")
    result = kit.check()
    assert_escalate(result, "QUORUM_UNAVAILABLE", "D2/judge-1: нет файла судьи")
    assert "D2/judge-3" in reasons_text(result)


def test_missing_r1_file_is_quorum_unavailable(kit: PanelKit) -> None:
    kit.delete(f"{PANEL}/r1/judge-2.md")
    assert_escalate(kit.check(), "QUORUM_UNAVAILABLE", "R1/judge-2")


def test_duplicate_seat_header_is_consensus_unavailable(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/d2/judge-2.md", "SEAT: judge-2", "SEAT: judge-1")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "дубликат seat")


def test_extra_judge_file_is_consensus_unavailable(kit: PanelKit) -> None:
    shutil.copy2(kit.panel / "d1" / "judge-1.md", kit.panel / "d1" / "judge-1-copy.md")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "лишний файл judge-1-copy.md")


def test_garbage_c1_is_consensus_unavailable_and_exit_2(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    kit.write(f"{PANEL}/c1/judge-2.md", "случайный мусор вместо ответа судьи\n")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "C1/judge-2")
    assert kit.run_verify() == 2
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "VERDICT: ESCALATE"
    assert any(line.startswith("GATE: BLOCKED.") for line in out)
    assert kit.read(".ai-team/verdict.md").startswith("Вердикт: ESCALATE\n\nverdict: null\n")


def test_unreadable_judge_file_is_consensus_unavailable(kit: PanelKit) -> None:
    (kit.panel / "d3" / "judge-3.md").write_bytes(b"\xff\xfe\x00 not utf-8 \x80")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "D3/judge-3")


def test_quorum_and_consensus_together_still_escalate(kit: PanelKit) -> None:
    kit.delete(f"{PANEL}/c1/judge-1.md")
    kit.write(f"{PANEL}/c1/judge-2.md", "мусор\n")
    result = kit.check()
    assert result.verdict == "ESCALATE"
    assert result.technical_status == "QUORUM_UNAVAILABLE"
    assert "C1/judge-2" in reasons_text(result)


# --------------------------------------------------------------------------- заголовок


def test_wrong_hat_breaks_rotation(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/d1/judge-1.md", "HAT: Реалист", "HAT: Скептик")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "по ротации ожидалась 'Реалист'")


def test_c1_hat_must_be_common(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/c1/judge-1.md", "HAT: Общая", "HAT: Скептик")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "HAT")


def test_wrong_round_in_header(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/d2/judge-1.md", "ROUND: D2", "ROUND: D1")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "ROUND")


def test_procedure_accepted_mismatch(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/r1/judge-3.md", gp.sha256_file(kit.panel / "manifest.json"), "0" * 64)
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "PROCEDURE_ACCEPTED")


def test_unknown_origin_is_rejected(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/r1/judge-1.md", "ORIGIN: reference-fixture", "ORIGIN: imagination")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "ORIGIN")


# --------------------------------------------------------------------------- C1


def test_wrong_c1_digest_is_consensus_unavailable(kit: PanelKit) -> None:
    digest = gp.sha256_file(kit.panel / "freeze.json")
    kit.replace(f"{PANEL}/c1/judge-2.md", digest, "f" * 64)
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "C1/judge-2: FREEZE_SHA256 не совпал")


def test_missing_fallback_consent_is_consensus_unavailable(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/c1/judge-3.md", "FALLBACK_CONSENT: YES\n", "")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "FALLBACK_CONSENT")


def test_missing_verdict_in_c1(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/c1/judge-1.md", "VERDICT: ACCEPT\n", "")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "нет VERDICT")


def test_single_objection_gives_consensual_reject_exit_1(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    kit.set_c1_verdicts({"judge-2": "REJECT"}, OBJECTION)
    result = kit.check()
    assert result.verdict == "REJECT", reasons_text(result)
    assert result.technical_status is None
    assert result.proof["verdict"] == "REJECT"
    assert "C1 judge-2: app/main.py:41 | пример возражения" in result.reasons
    assert kit.run_verify() == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "VERDICT: REJECT"
    assert any(line.startswith("GATE: REWORK.") for line in out)
    assert kit.read(".ai-team/verdict.md").startswith("Вердикт: REWORK\n\nVERDICT: REJECT\n")


def test_reject_without_objection_against_accept_candidate(kit: PanelKit) -> None:
    kit.set_c1_verdicts({"judge-2": "REJECT"})
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "без OBJECTION")


def test_objection_must_have_location_and_defect(kit: PanelKit) -> None:
    kit.set_c1_verdicts({"judge-2": "REJECT"}, "без локации")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "OBJECTION")


# --------------------------------------------------------------------------- устаревший пакет


@pytest.mark.parametrize(
    ("rel", "key"),
    [
        ("specs/LINK-42-enable-link.md", "spec"),
        ("docs/risk-plan-LINK-42.md", "risk_plan"),
        ("docs/gate-rubric.md", "rubric"),
        (".ai-team/handoff-coder.md", "coder_handoff"),
        (".ai-team/code-gate.json", "code_gate"),
    ],
)
def test_changed_input_makes_package_stale(kit: PanelKit, rel: str, key: str) -> None:
    kit.write(rel, kit.read(rel) + "\n ")
    assert_escalate(kit.check(), "STALE_PACKAGE", f"sha256 входа {key} не совпал")


def test_missing_manifest_is_stale(kit: PanelKit) -> None:
    kit.delete(f"{PANEL}/manifest.json")
    assert_escalate(kit.check(), "STALE_PACKAGE", "нет panel/manifest.json")


def test_missing_input_file_is_stale(kit: PanelKit) -> None:
    kit.delete("docs/risk-plan-LINK-42.md")
    assert_escalate(kit.check(), "STALE_PACKAGE", "нет входного файла risk_plan")


def test_code_gate_bound_to_old_spec_is_stale(kit: PanelKit) -> None:
    gate = json.loads(kit.read(".ai-team/code-gate.json"))
    gate["inputs_sha256"]["spec"] = "0" * 64
    kit.write(".ai-team/code-gate.json", json.dumps(gate, indent=2) + "\n")
    gp.write_manifest(kit.team, kit.root, pass_id="x")  # манифест перепривязан, привязка гейта нет
    assert_escalate(kit.check(), "STALE_PACKAGE", "code-gate.json устарел: sha256 входа spec")


def test_red_code_gate_command_is_code_gate_red(kit: PanelKit) -> None:
    gate = json.loads(kit.read(".ai-team/code-gate.json"))
    gate["commands"][2]["exit_code"] = 1
    kit.write(".ai-team/code-gate.json", json.dumps(gate, indent=2) + "\n")
    kit.repin()
    assert_escalate(kit.check(), "CODE_GATE_RED", "красный")


def test_missing_required_gate_command_is_code_gate_red(kit: PanelKit) -> None:
    gate = json.loads(kit.read(".ai-team/code-gate.json"))
    gate["commands"] = [c for c in gate["commands"] if "mutate_probe" not in c["cmd"]]
    kit.write(".ai-team/code-gate.json", json.dumps(gate, indent=2) + "\n")
    kit.repin()
    assert_escalate(kit.check(), "CODE_GATE_RED", "нет команды `mutate_probe`")


def test_missing_blast_radius_gate_command_is_code_gate_red(kit: PanelKit) -> None:
    gate = json.loads(kit.read(".ai-team/code-gate.json"))
    gate["commands"] = [c for c in gate["commands"] if "check-blast-radius" not in c["cmd"]]
    kit.write(".ai-team/code-gate.json", json.dumps(gate, indent=2) + "\n")
    kit.repin()
    assert_escalate(kit.check(), "CODE_GATE_RED", "нет команды `check-blast-radius`")


def test_garbage_manifest_is_consensus_unavailable(kit: PanelKit) -> None:
    kit.write(f"{PANEL}/manifest.json", "{не json")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "manifest.json")


# --------------------------------------------------------------------------- реестр и freeze


def test_lost_row_in_ledger_file_is_detected(kit: PanelKit) -> None:
    lines = kit.read(f"{PANEL}/findings-ledger.tsv").splitlines()
    kit.write(f"{PANEL}/findings-ledger.tsv", "\n".join(lines[:3] + lines[4:]) + "\n")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "findings-ledger.tsv расходится")


def test_doubled_row_in_ledger_file_is_detected(kit: PanelKit) -> None:
    lines = kit.read(f"{PANEL}/findings-ledger.tsv").splitlines()
    kit.write(f"{PANEL}/findings-ledger.tsv", "\n".join([*lines, lines[1]]) + "\n")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "findings-ledger.tsv расходится")


def test_ledger_md_must_match_tsv(kit: PanelKit) -> None:
    kit.write(f"{PANEL}/findings-ledger.md", kit.read(f"{PANEL}/findings-ledger.md") + "лишнее\n")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "findings-ledger.md расходится")


def test_ledger_diverges_from_round_files(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/r1/judge-2.md", "добавить вторую проверку", "добавить третью проверку")
    assert_escalate(
        kit.check(), "CONSENSUS_UNAVAILABLE", "findings-ledger.tsv расходится с файлами раундов"
    )


def test_missing_ledger_file(kit: PanelKit) -> None:
    kit.delete(f"{PANEL}/findings-ledger.tsv")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "нет findings-ledger.tsv")


def test_freeze_must_match_recalculation(kit: PanelKit) -> None:
    freeze = json.loads(kit.read(f"{PANEL}/freeze.json"))
    freeze["candidate"] = "REJECT"
    kit.write(f"{PANEL}/freeze.json", json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    result = kit.check()
    assert result.technical_status == "CONSENSUS_UNAVAILABLE"
    assert "freeze.json расходится" in reasons_text(result)


def test_missing_freeze_file(kit: PanelKit) -> None:
    kit.delete(f"{PANEL}/freeze.json")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "нет freeze.json")


# --------------------------------------------------------------------------- дерево кода


def test_code_tree_hash_is_bound_in_manifest_freeze_and_proof(kit: PanelKit) -> None:
    code_tree = gp.compute_code_tree_sha256(kit.root)
    assert json.loads(kit.read(f"{PANEL}/manifest.json"))["inputs_sha256"][gp.CODE_TREE_KEY] == (
        code_tree
    )
    assert json.loads(kit.read(f"{PANEL}/freeze.json"))[gp.CODE_TREE_KEY] == code_tree
    assert json.loads(kit.read(".ai-team/consensus-proof.json"))[gp.CODE_TREE_KEY] == code_tree
    assert kit.check().proof[gp.CODE_TREE_KEY] == code_tree


def test_code_tree_hash_ignores_caches_and_sees_every_change(kit: PanelKit) -> None:
    base = gp.compute_code_tree_sha256(kit.root)
    kit.write("app/__pycache__/main.cpython-314.pyc", "кэш")
    kit.write("tests/__pycache__/x.pyc", "кэш")
    assert gp.compute_code_tree_sha256(kit.root) == base
    kit.write("app/новый_модуль.py", "X = 1\n")
    added = gp.compute_code_tree_sha256(kit.root)
    assert added != base
    kit.delete("app/новый_модуль.py")
    assert gp.compute_code_tree_sha256(kit.root) == base
    kit.delete("alembic/script.py.mako")
    assert gp.compute_code_tree_sha256(kit.root) != base


@pytest.mark.parametrize(
    "rel",
    ["app/main.py", "tests/conftest.py", "alembic/env.py", "pyproject.toml"],
)
def test_code_changed_after_init_is_stale_code_tree(kit: PanelKit, rel: str) -> None:
    kit.write(rel, kit.read(rel) + "\n# правка после init прохода\n")
    assert_escalate(kit.check(), "STALE_PACKAGE", "STALE_CODE_TREE")


def test_code_changed_after_init_blocks_freeze_and_verify(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    kit.write("app/main.py", kit.read("app/main.py") + "\n# правка после init прохода\n")
    with pytest.raises(gp.PanelFormatError, match="STALE_CODE_TREE"):
        gp.write_freeze(kit.team, kit.root)
    assert gp.main(["freeze", str(kit.team)], kit.root) == 2
    assert "STALE_CODE_TREE" in capsys.readouterr().err
    assert kit.run_verify() == 2
    out = capsys.readouterr().out
    assert "STALE_CODE_TREE" in out
    assert out.strip().splitlines()[-1] == "VERDICT: ESCALATE"
    assert json.loads(kit.read(".ai-team/consensus-proof.json"))["technical_status"] == (
        "STALE_PACKAGE"
    )


def test_manifest_without_code_tree_is_rejected(kit: PanelKit) -> None:
    manifest = json.loads(kit.read(f"{PANEL}/manifest.json"))
    del manifest["inputs_sha256"][gp.CODE_TREE_KEY]
    kit.write(f"{PANEL}/manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "code_tree_sha256")


def test_freeze_with_foreign_code_tree_is_detected(kit: PanelKit) -> None:
    freeze = json.loads(kit.read(f"{PANEL}/freeze.json"))
    freeze[gp.CODE_TREE_KEY] = "0" * 64
    kit.write(f"{PANEL}/freeze.json", json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    result = kit.check()
    assert result.technical_status == "CONSENSUS_UNAVAILABLE"
    assert "freeze.json расходится" in reasons_text(result)


# --------------------------------------------------------------------------- правила позиций


def test_position_change_without_arg_or_new_is_rejected(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/d2/judge-2.md",
        "| ARG: «StripePaymentGateway",
        "| evidence: «StripePaymentGateway",
    )
    assert_escalate(
        kit.check(), "CONSENSUS_UNAVAILABLE", "смена позиции DISPUTE->AGREE без ARG:/NEW:"
    )


def test_author_change_from_agree_requires_arg_or_new(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/d1/judge-1.md",
        "POSITION F-002: WITHDRAW | NEW:",
        "POSITION F-002: WITHDRAW | evidence:",
    )
    assert_escalate(
        kit.check(), "CONSENSUS_UNAVAILABLE", "смена позиции AGREE->WITHDRAW без ARG:/NEW:"
    )


def test_position_without_any_text_is_rejected(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/d1/judge-1.md",
        "POSITION F-003: AGREE | evidence: tests/flat_api/test_link_toggle.py:46-51 проверяет только подстроку secret-auth-key",
        "POSITION F-003: AGREE",
    )
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "нет непустого evidence:/ARG:/NEW:")


def test_missing_position_on_open_finding(kit: PanelKit) -> None:
    lines = kit.read(f"{PANEL}/d1/judge-3.md").splitlines()
    kit.write(
        f"{PANEL}/d1/judge-3.md", "\n".join(x for x in lines if "POSITION F-004" not in x) + "\n"
    )
    assert_escalate(
        kit.check(), "CONSENSUS_UNAVAILABLE", "D1/judge-3: нет позиции по открытой F-004"
    )


def test_double_position_on_one_finding(kit: PanelKit) -> None:
    kit.add_line(f"{PANEL}/d1/judge-3.md", "POSITION F-004: AGREE | evidence: ещё раз")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "две позиции по F-004")


def test_position_on_unknown_finding(kit: PanelKit) -> None:
    kit.add_line(f"{PANEL}/d1/judge-3.md", "POSITION F-099: AGREE | evidence: нет такой")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "позиция по неизвестной F-099")


def test_positions_on_closed_findings_are_ignored(kit: PanelKit) -> None:
    kit.add_line(
        f"{PANEL}/d3/judge-2.md",
        "POSITION F-003: DISPUTE | evidence: закрыта в D1, позиция игнорируется",
    )
    assert kit.check().verdict == "READY"


def test_amend_by_non_author_is_rejected(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/d1/judge-1.md",
        "POSITION F-003: AGREE | evidence: tests/flat_api/test_link_toggle.py:46-51",
        "POSITION F-003: AMEND | severity=IMPORTANT | NEW: чужая находка",
    )
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "AMEND допустим только автору находки")


def test_amend_without_severity_is_rejected(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/d2/judge-3.md", "AMEND | severity=MINOR | NEW:", "AMEND | NEW:")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "AMEND требует severity=")


def test_amend_to_same_severity_is_rejected(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/d2/judge-3.md", "severity=MINOR | NEW:", "severity=IMPORTANT | NEW:")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "AMEND не меняет тяжесть")


def hold_f004_downgrade_against_amend(kit: PanelKit, rounds: tuple[str, ...]) -> None:
    """Автор F-004 (judge-3) подаёт AMEND MINOR в перечисленных раундах, коллеги спорят."""
    if "d1" in rounds:
        kit.replace(
            f"{PANEL}/d1/judge-3.md",
            "POSITION F-004: AGREE | evidence:",
            "POSITION F-004: AMEND | severity=MINOR | NEW:",
        )
    if "d3" in rounds:
        kit.replace(
            f"{PANEL}/d3/judge-3.md",
            "POSITION F-004: AGREE | ARG:",
            "POSITION F-004: AMEND | severity=MINOR | ARG:",
        )
        for seat in ("judge-1", "judge-2"):
            kit.replace(
                f"{PANEL}/d3/{seat}.md",
                "POSITION F-004: AGREE | ARG:",
                "POSITION F-004: DISPUTE | ARG:",
            )


def test_author_amend_downgrade_is_held_while_colleagues_dispute(kit: PanelKit) -> None:
    """RW-001: AMEND MINOR в D1..D3 при DISPUTE двух коллег не снимает блокирующую тяжесть."""
    hold_f004_downgrade_against_amend(kit, ("d1", "d3"))
    rows = {r.f_id: r for r in gp.build_ledger(kit.panel)}
    row = rows["F-004"]
    assert (row.severity, row.status) == ("IMPORTANT", "OPEN")
    assert row.resolution == "D3:amend-pending-MINOR"
    assert gp.candidate_for(list(rows.values())) == "REJECT"
    kit.rechain()
    freeze = json.loads(kit.read(f"{PANEL}/freeze.json"))
    assert (freeze["candidate"], freeze["open_blocking"]) == ("REJECT", 1)


def test_amend_downgrade_pending_after_d1_is_not_applied_before_unanimity(kit: PanelKit) -> None:
    hold_f004_downgrade_against_amend(kit, ("d1",))
    for rnd in ("d2", "d3"):
        kit.delete(f"{PANEL}/{rnd}")
    row = {r.f_id: r for r in gp.build_ledger(kit.panel)}["F-004"]
    assert (row.severity, row.status, row.resolution) == (
        "IMPORTANT",
        "OPEN",
        "D1:amend-pending-MINOR",
    )


def test_amend_downgrade_applies_when_both_colleagues_agree_in_same_round(kit: PanelKit) -> None:
    hold_f004_downgrade_against_amend(kit, ("d1",))
    for seat in ("judge-1", "judge-2"):
        kit.replace(
            f"{PANEL}/d1/{seat}.md",
            "POSITION F-004: DISPUTE | evidence:",
            "POSITION F-004: AGREE | evidence:",
        )
    for rnd in ("d2", "d3"):
        kit.delete(f"{PANEL}/{rnd}")
    row = {r.f_id: r for r in gp.build_ledger(kit.panel)}["F-004"]
    assert (row.severity, row.status, row.resolution) == ("MINOR", "AGREED", "D1:agree-3/3")


def test_amend_upgrade_applies_at_once_and_stays_open(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/d1/judge-2.md",
        "POSITION F-003: AGREE | evidence:",
        "POSITION F-003: AMEND | severity=IMPORTANT | NEW:",
    )
    for rnd in ("d2", "d3"):
        kit.delete(f"{PANEL}/{rnd}")
    row = {r.f_id: r for r in gp.build_ledger(kit.panel)}["F-003"]
    assert (row.severity, row.status, row.resolution) == (
        "IMPORTANT",
        "OPEN",
        "D1:amended-IMPORTANT",
    )


def test_severity_outside_amend_is_rejected(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/d1/judge-1.md",
        "POSITION F-004: DISPUTE | evidence:",
        "POSITION F-004: DISPUTE | severity=MINOR | evidence:",
    )
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "severity= допустим только в AMEND")


def test_withdraw_by_non_author_counts_as_not_agree(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/d1/judge-2.md",
        "POSITION F-002: DISPUTE | evidence: app/schemas",
        "POSITION F-002: WITHDRAW | evidence: app/schemas",
    )
    result = kit.check()
    assert result.verdict == "READY", reasons_text(result)
    assert {r.f_id: r.status for r in result.ledger_rows}["F-002"] == "WITHDRAWN"


def test_withdraw_is_blocked_by_one_agree(kit: PanelKit) -> None:
    for rnd in ("d2", "d3"):
        kit.delete(f"{PANEL}/{rnd}")
    kit.replace(
        f"{PANEL}/d1/judge-2.md",
        "POSITION F-002: DISPUTE | evidence:",
        "POSITION F-002: AGREE | evidence:",
    )
    row = {r.f_id: r for r in gp.build_ledger(kit.panel)}["F-002"]
    assert (row.status, row.resolution) == ("OPEN", "D1:unresolved")


def test_two_agree_one_dispute_is_not_agreed(kit: PanelKit) -> None:
    """Большинства 2/3 нет: согласие только 3/3, иначе находка остаётся открытой."""
    for rnd in ("d2", "d3"):
        kit.delete(f"{PANEL}/{rnd}")
    kit.replace(
        f"{PANEL}/d1/judge-3.md",
        "POSITION F-003: AGREE | evidence:",
        "POSITION F-003: DISPUTE | evidence:",
    )
    row = {r.f_id: r for r in gp.build_ledger(kit.panel)}["F-003"]
    assert (row.status, row.resolution) == ("OPEN", "D1:unresolved")


def test_d_without_answers_section_is_rejected(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/d1/judge-1.md", "## Ответы на вопросы коллег", "## Ответы")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "обе секции")


def test_d_without_questions_section_is_rejected(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/d2/judge-1.md", "## Вопросы коллегам (к следующему раунду)", "## Вопросы")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "обе секции")


def test_d3_with_new_question_is_hidden_d4(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/d3/judge-1.md", "- вопросов нет", "- judge-2: ещё один вопрос")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "D3: в секции вопросов допустимо только")


def test_d3_questions_may_say_no_questions(kit: PanelKit) -> None:
    assert kit.check().verdict == "READY"


# --------------------------------------------------------------------------- формат R1


def test_r1_requires_coverage(kit: PanelKit) -> None:
    lines = kit.read(f"{PANEL}/r1/judge-1.md").splitlines()
    kit.write(
        f"{PANEL}/r1/judge-1.md", "\n".join(x for x in lines if not x.startswith("COVERAGE")) + "\n"
    )
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "нет строки COVERAGE")


def test_r1_coverage_needs_all_five_keys(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/r1/judge-1.md",
        "COVERAGE: 1=OK 2=OK 3=OK 4=OK 5=ISSUE",
        "COVERAGE: 1=OK 2=OK 3=OK 4=OK",
    )
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "COVERAGE")


def test_r1_findings_none_conflicts_with_findings(kit: PanelKit) -> None:
    kit.add_line(f"{PANEL}/r1/judge-1.md", "FINDINGS: none")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "R1: нужен либо")


def test_r1_without_findings_declaration(kit: PanelKit) -> None:
    kit.write(f"{PANEL}/r1/judge-3.md", kit.read(f"{PANEL}/r1/judge-3.md").split("FINDING C1")[0])
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "R1: нужен либо")


def test_finding_with_unknown_severity(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/r1/judge-2.md", "FINDING B1: MINOR", "FINDING B1: CRITICAL")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "неверная строка FINDING")


def test_finding_location_must_be_file_line(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/r1/judge-2.md",
        "tests/flat_api/test_link_toggle.py:51 |",
        "tests/flat_api/test_link_toggle.py |",
    )
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "location должен быть file:line")


def test_finding_summary_must_not_contain_pipe(kit: PanelKit) -> None:
    kit.replace(f"{PANEL}/r1/judge-2.md", "добавить вторую проверку", "добавить | вторую проверку")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "FINDING B1")


def test_finding_is_not_allowed_in_c1(kit: PanelKit) -> None:
    kit.add_line(f"{PANEL}/c1/judge-1.md", "FINDING Z1: MINOR | app/main.py:1 | новая находка в C1")
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "недопустима в этом раунде")


def test_zero_findings_debate_still_needs_all_three_d_rounds(kit: PanelKit) -> None:
    """Ноль находок: R1 даёт `FINDINGS: none`, D1..D3 обязательны, кандидат ACCEPT."""
    for seat in gp.SEATS:
        coverage = "COVERAGE: 1=OK 2=OK 3=OK 4=OK 5=OK\nFINDINGS: none\n"
        head = kit.read(f"{PANEL}/r1/{seat}.md").split("COVERAGE:")[0]
        kit.write(f"{PANEL}/r1/{seat}.md", head + coverage)
        for rnd in ("d1", "d2", "d3"):
            text = kit.read(f"{PANEL}/{rnd}/{seat}.md")
            kit.write(
                f"{PANEL}/{rnd}/{seat}.md",
                text.split("## Ответы")[0]
                + "## Ответы на вопросы коллег\n- вопросов не было\n"
                + "## Вопросы коллегам (к следующему раунду)\n- вопросов нет\n",
            )
    kit.rechain()
    result = kit.check()
    assert result.verdict == "READY", reasons_text(result)
    assert result.ledger_rows == []
    assert kit.read(f"{PANEL}/findings-ledger.tsv") == gp.LEDGER_HEADER + "\n"
    kit.delete(f"{PANEL}/d3/judge-2.md")
    assert_escalate(kit.check(), "QUORUM_UNAVAILABLE", "D3/judge-2")


# --------------------------------------------------------------------------- блокирующие находки


def agree_f004_as_important(kit: PanelKit) -> None:
    """F-004 остаётся IMPORTANT: автор не понижает тяжесть, в D3 все трое согласны."""
    kit.replace(
        f"{PANEL}/d2/judge-3.md",
        "POSITION F-004: AMEND | severity=MINOR | NEW:",
        "POSITION F-004: AGREE | evidence:",
    )
    kit.rechain()


def test_agreed_important_makes_reject_candidate(kit: PanelKit) -> None:
    agree_f004_as_important(kit)
    freeze = json.loads(kit.read(f"{PANEL}/freeze.json"))
    assert freeze["candidate"] == "REJECT"
    assert freeze["agreed_blocking"] == 1
    assert freeze["open_blocking"] == 0
    row = {r.f_id: r for r in gp.build_ledger(kit.panel)}["F-004"]
    assert (row.severity, row.status, row.resolution) == ("IMPORTANT", "AGREED", "D3:agree-3/3")


def test_accept_votes_contradict_reject_candidate(kit: PanelKit) -> None:
    agree_f004_as_important(kit)
    assert_escalate(
        kit.check(), "CONSENSUS_UNAVAILABLE", "C1: ACCEPT противоречит кандидату REJECT"
    )


def test_single_accept_against_reject_candidate_is_consensus_unavailable(kit: PanelKit) -> None:
    agree_f004_as_important(kit)
    kit.set_c1_verdicts({"judge-1": "REJECT", "judge-2": "REJECT"})
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "противоречит кандидату")


def test_three_rejects_on_reject_candidate_is_agreed_reject(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    agree_f004_as_important(kit)
    kit.set_c1_verdicts(ALL_REJECT)
    result = kit.check()
    assert result.verdict == "REJECT", reasons_text(result)
    assert any(reason.startswith("F-004 IMPORTANT AGREED") for reason in result.reasons)
    assert kit.run_verify() == 1
    assert capsys.readouterr().out.strip().splitlines()[-1] == "VERDICT: REJECT"


def test_open_important_after_d3_is_reject_candidate(kit: PanelKit) -> None:
    kit.replace(
        f"{PANEL}/d1/judge-1.md",
        "POSITION F-002: WITHDRAW | NEW:",
        "POSITION F-002: AGREE | evidence:",
    )
    for rnd in ("d2", "d3"):
        kit.add_line(
            f"{PANEL}/{rnd}/judge-1.md", "POSITION F-002: AGREE | evidence: app/main.py:41"
        )
        kit.add_line(
            f"{PANEL}/{rnd}/judge-2.md",
            "POSITION F-002: DISPUTE | evidence: app/schemas/link.py:15-19",
        )
        kit.add_line(
            f"{PANEL}/{rnd}/judge-3.md",
            "POSITION F-002: DISPUTE | evidence: app/schemas/validators.py:40-51",
        )
    kit.rechain()
    row = {r.f_id: r for r in gp.build_ledger(kit.panel)}["F-002"]
    assert (row.severity, row.status, row.resolution) == ("IMPORTANT", "OPEN", "D3:unresolved")
    freeze = json.loads(kit.read(f"{PANEL}/freeze.json"))
    assert (freeze["candidate"], freeze["open_blocking"]) == ("REJECT", 1)
    kit.set_c1_verdicts(ALL_REJECT)
    assert kit.check().verdict == "REJECT"


def test_new_finding_in_d3_stays_unresolved(kit: PanelKit) -> None:
    kit.add_line(
        f"{PANEL}/d3/judge-2.md",
        "NEW-FINDING N9: IMPORTANT | app/main.py:7 | поздняя находка без обсуждения",
    )
    kit.rechain()
    row = {r.f_id: r for r in gp.build_ledger(kit.panel)}["F-006"]
    assert (row.judge, row.status, row.resolution) == ("judge-2", "OPEN", "D3:unresolved")
    assert json.loads(kit.read(f"{PANEL}/freeze.json"))["candidate"] == "REJECT"


def test_new_finding_in_d1_is_debated_in_next_rounds(kit: PanelKit) -> None:
    row = {r.f_id: r for r in gp.build_ledger(kit.panel)}["F-005"]
    assert (row.judge, row.status, row.resolution) == ("judge-2", "AGREED", "D2:agree-3/3")
    lines = kit.read(f"{PANEL}/d2/judge-1.md").splitlines()
    kit.write(
        f"{PANEL}/d2/judge-1.md", "\n".join(x for x in lines if "POSITION F-005" not in x) + "\n"
    )
    assert_escalate(
        kit.check(), "CONSENSUS_UNAVAILABLE", "D2/judge-1: нет позиции по открытой F-005"
    )


# --------------------------------------------------------------------------- ledger: модуль


def test_ledger_roundtrip_and_markdown_projection(kit: PanelKit) -> None:
    rows = gp.build_ledger(kit.panel)
    tsv = gp.render_ledger_tsv(rows)
    assert gp.parse_ledger_tsv(tsv) == rows
    assert tsv.splitlines()[0] == gp.LEDGER_HEADER
    sha = gp.sha256_text(tsv)
    md = gp.render_ledger_md(rows, sha)
    assert md.splitlines()[0].endswith(sha)
    assert md.count("\n| F-") == len(rows)


def test_empty_ledger_is_only_header() -> None:
    assert gp.render_ledger_tsv([]) == gp.LEDGER_HEADER + "\n"
    assert gp.parse_ledger_tsv(gp.LEDGER_HEADER + "\n") == []


@pytest.mark.parametrize(
    "text",
    [
        "f_id\tseverity\n",
        gp.LEDGER_HEADER + "\nF-001\tMINOR\tjudge-1\ta.py:1\tтекст\tAGREED\n",
        gp.LEDGER_HEADER + "\nF-1\tMINOR\tjudge-1\ta.py:1\tтекст\tAGREED\tD1:agree-3/3\n",
        gp.LEDGER_HEADER + "\nF-001\tHUGE\tjudge-1\ta.py:1\tтекст\tAGREED\tD1:agree-3/3\n",
        gp.LEDGER_HEADER + "\nF-001\tMINOR\tjudge-9\ta.py:1\tтекст\tAGREED\tD1:agree-3/3\n",
        gp.LEDGER_HEADER + "\nF-001\tMINOR\tjudge-1\ta.py:1\tтекст\tDONE\tD1:agree-3/3\n",
        gp.LEDGER_HEADER
        + "\nF-001\tMINOR\tjudge-1\ta.py:1\tтекст\tOPEN\tD3:unresolved\n"
        + "F-001\tMINOR\tjudge-1\ta.py:1\tтекст\tOPEN\tD3:unresolved\n",
        gp.LEDGER_HEADER + "\r\n",
    ],
)
def test_parse_ledger_rejects_bad_tsv(text: str) -> None:
    with pytest.raises(gp.PanelFormatError):
        gp.parse_ledger_tsv(text)


def test_build_ledger_after_r1_only(kit: PanelKit) -> None:
    for rnd in ("d1", "d2", "d3"):
        kit.delete(f"{PANEL}/{rnd}")
    rows = gp.build_ledger(kit.panel)
    assert [r.f_id for r in rows] == ["F-001", "F-002", "F-003", "F-004"]
    assert {r.status for r in rows} == {"OPEN"}


def test_build_ledger_raises_on_broken_round(kit: PanelKit) -> None:
    kit.delete(f"{PANEL}/d1/judge-2.md")
    with pytest.raises(gp.PanelFormatError, match="D1/judge-2: нет файла судьи"):
        gp.build_ledger(kit.panel)


def test_f_ids_follow_judge_order_then_new_findings(kit: PanelKit) -> None:
    rows = gp.build_ledger(kit.panel)
    assert [(r.f_id, r.judge) for r in rows] == [
        ("F-001", "judge-1"),
        ("F-002", "judge-1"),
        ("F-003", "judge-2"),
        ("F-004", "judge-3"),
        ("F-005", "judge-2"),
    ]


def test_rotation_table_matches_contract() -> None:
    assert gp.ROUNDS == ("R1", "D1", "D2", "D3", "C1")
    assert gp.SEATS == ("judge-1", "judge-2", "judge-3")
    assert [gp.ROTATION["R1"][s] for s in gp.SEATS] == ["Скептик", "Реалист", "Визионер"]
    assert [gp.ROTATION["D1"][s] for s in gp.SEATS] == ["Реалист", "Визионер", "Скептик"]
    assert [gp.ROTATION["D2"][s] for s in gp.SEATS] == ["Визионер", "Скептик", "Реалист"]
    assert gp.ROTATION["D3"] == gp.ROTATION["R1"]
    assert set(gp.ROTATION["C1"].values()) == {"Общая"}


# --------------------------------------------------------------------------- CLI


def test_cli_sha256_single_and_multiple(kit: PanelKit, capsys: pytest.CaptureFixture[str]) -> None:
    spec = kit.path("specs/LINK-42-enable-link.md")
    assert gp.main(["sha256", str(spec)], kit.root) == 0
    assert capsys.readouterr().out.strip() == gp.sha256_file(spec)
    rubric = kit.path("docs/gate-rubric.md")
    assert gp.main(["sha256", str(spec), str(rubric)], kit.root) == 0
    assert capsys.readouterr().out.strip().splitlines() == [
        f"{gp.sha256_file(spec)}  {spec}",
        f"{gp.sha256_file(rubric)}  {rubric}",
    ]


def test_cli_sha256_missing_file_exit_2(kit: PanelKit, capsys: pytest.CaptureFixture[str]) -> None:
    assert gp.main(["sha256", str(kit.root / "нет.txt")], kit.root) == 2
    assert "ОШИБКА" in capsys.readouterr().err
    assert gp.main(["sha256"], kit.root) == 2


def test_cli_manifest_is_deterministic_and_reproduces_reference(
    kit: PanelKit, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENCODE_MODEL", raising=False)
    before = kit.read(f"{PANEL}/manifest.json")
    pass_id = json.loads(before)["pass_id"]
    assert gp.main(["manifest", str(kit.team), "--pass-id", pass_id], kit.root) == 0
    assert capsys.readouterr().out.strip() == gp.sha256_file(kit.panel / "manifest.json")
    assert kit.read(f"{PANEL}/manifest.json") == before
    assert gp.main(["manifest", str(kit.team)], kit.root) == 0
    assert kit.read(f"{PANEL}/manifest.json") == before


def test_cli_manifest_options_and_default_pass_id(
    kit: PanelKit, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENCODE_MODEL", raising=False)
    assert gp.main(["manifest", str(kit.team), "--model", "m-1", "--cycle", "3"], kit.root) == 0
    data = json.loads(kit.read(f"{PANEL}/manifest.json"))
    assert (data["model"], data["cycle"], data["calls_budget"]) == ("m-1", 3, 15)
    assert data["pass_id"].startswith("LINK-42-c3-")
    assert list(data) == sorted(data)
    assert_escalate(kit.check(), "CONSENSUS_UNAVAILABLE", "PROCEDURE_ACCEPTED")


def test_cli_manifest_model_from_environment(
    kit: PanelKit, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENCODE_MODEL", "opencode/deepseek-v4.1-env")
    assert gp.main(["manifest", str(kit.team)], kit.root) == 0
    assert json.loads(kit.read(f"{PANEL}/manifest.json"))["model"] == "opencode/deepseek-v4.1-env"


def test_cli_manifest_without_inputs_exit_2(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    kit.delete(".ai-team/code-gate.json")
    assert gp.main(["manifest", str(kit.team)], kit.root) == 2
    assert "нет входного файла code_gate" in capsys.readouterr().err


def test_cli_ledger_and_freeze_reproduce_reference(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger_before = kit.read(f"{PANEL}/findings-ledger.tsv")
    md_before = kit.read(f"{PANEL}/findings-ledger.md")
    freeze_before = kit.read(f"{PANEL}/freeze.json")
    assert gp.main(["ledger", str(kit.team)], kit.root) == 0
    assert capsys.readouterr().out.strip() == gp.sha256_file(kit.panel / "findings-ledger.tsv")
    assert gp.main(["freeze", str(kit.team)], kit.root) == 0
    assert capsys.readouterr().out.strip() == gp.sha256_file(kit.panel / "freeze.json")
    assert kit.read(f"{PANEL}/findings-ledger.tsv") == ledger_before
    assert kit.read(f"{PANEL}/findings-ledger.md") == md_before
    assert kit.read(f"{PANEL}/freeze.json") == freeze_before


def test_cli_ledger_on_broken_files_exit_2(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    kit.delete(f"{PANEL}/r1/judge-1.md")
    assert gp.main(["ledger", str(kit.team)], kit.root) == 2
    assert "R1/judge-1" in capsys.readouterr().err


def test_cli_freeze_requires_fresh_ledger(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    kit.delete(f"{PANEL}/findings-ledger.tsv")
    assert gp.main(["freeze", str(kit.team)], kit.root) == 2
    assert "ledger" in capsys.readouterr().err


def test_cli_freeze_digest_is_what_c1_signs(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    gp.main(["freeze", str(kit.team)], kit.root)
    digest = capsys.readouterr().out.strip()
    for seat in gp.SEATS:
        assert f"FREEZE_SHA256: {digest}" in kit.read(f"{PANEL}/c1/{seat}.md")


def test_cli_default_arguments_use_project_root(
    kit: PanelKit, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gp.main([], kit.root) == 0
    assert (kit.root / "handoff" / "03-gate-proof.json").is_file()
    assert capsys.readouterr().out.strip().splitlines()[-1] == "VERDICT: READY"
    assert gp.main(["verify"], kit.root) == 0


def test_run_checks_failure_escalates_code_gate_red(
    kit: PanelKit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gp, "run_live_checks", fake_checks(pytest_code=1))
    assert (
        gp.main(
            [str(kit.team), str(kit.root / "handoff" / "03-gate-proof.json"), "--run-checks"],
            kit.root,
        )
        == 2
    )
    assert capsys.readouterr().out.strip().splitlines()[-1] == "VERDICT: ESCALATE"
    proof = json.loads(kit.read(".ai-team/consensus-proof.json"))
    assert (proof["verdict"], proof["technical_status"]) == (None, "CODE_GATE_RED")
    gate_proof = json.loads(kit.read("handoff/03-gate-proof.json"))
    assert gate_proof["checks_exit_codes"] == {"ruff_check": 0, "pytest": 1}


def test_run_checks_green_keeps_ready(kit: PanelKit, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gp, "run_live_checks", fake_checks(pytest_code=0))
    assert (
        gp.main(
            [str(kit.team), str(kit.root / "handoff" / "03-gate-proof.json"), "--run-checks"],
            kit.root,
        )
        == 0
    )
    gate_proof = json.loads(kit.read("handoff/03-gate-proof.json"))
    assert gate_proof["checks_exit_codes"] == {"ruff_check": 0, "pytest": 0}


# --------------------------------------------------------------------------- запуск скрипта


def test_script_runs_standalone_fast_and_deterministically(kit: PanelKit) -> None:
    """Скрипт из копии дерева: корень берётся по расположению файла, цель < 2 с, вывод стабилен."""
    shutil.copytree(
        Path(gp.__file__).resolve().parent,
        kit.root / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", "test_*", "conftest.py"),
    )
    started = time.monotonic()
    done = subprocess.run(
        [sys.executable, "scripts/generate_proof.py"],
        cwd=kit.root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    elapsed = time.monotonic() - started
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip().splitlines()[-1] == "VERDICT: READY"
    assert "GATE: PASS. Протокол: handoff/03-gate-proof.json" in done.stdout
    assert elapsed < 2.0
