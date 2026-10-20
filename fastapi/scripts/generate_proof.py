#!/usr/bin/env python3
"""Сборка протокола Gate-панели LINK-42 из настоящих голосов и настоящих проверок.

Скрипт ничего не придумывает: он читает файлы голосов судей из `--votes-dir`
(по умолчанию `.ai-team/panel-votes/*.json`), проверяет, что голоса относятся к текущим
версиям спеки и риск-плана (sha256), запускает `ruff check` и `pytest` и только после этого
пишет протокол. Нет голосов, нет кворума или красная проверка: статус BLOCKED и код 1.

Каждый seat (судья) должен быть уникальным: набор с дубликатами отклоняется целиком.

Формат голоса: {"seat", "verdict": "READY" | "REWORK", "finding", "origin", "task_id",
"inputs_sha256": {"spec", "risk_plan"}}. Кворум по скилу pipeline: минимум 3 голоса,
минимум 2 из них READY.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
SPEC = Path("specs/LINK-42-enable-link.md")
RISK_PLAN = Path("docs/risk-plan-LINK-42.md")
POSITIVE = {"READY", "PASS"}
MIN_VOTES = 3
MIN_POSITIVE = 2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def load_votes(votes_dir: Path, inputs: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    votes: list[dict[str, Any]] = []
    problems: list[str] = []
    seats: dict[str, str] = {}
    duplicates: list[str] = []
    if not votes_dir.is_dir():
        return votes, [f"каталог голосов не найден: {votes_dir}"]
    for path in sorted(votes_dir.glob("*.json")):
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: невалидный JSON ({exc})")
            continue
        if not isinstance(raw, dict):
            problems.append(f"{path.name}: голос должен быть JSON-объектом")
            continue
        vote = cast(dict[str, Any], raw)
        missing = [k for k in ("seat", "verdict", "finding", "inputs_sha256") if not vote.get(k)]
        if missing:
            problems.append(f"{path.name}: нет полей {missing}")
            continue
        seat = vote["seat"]
        if not isinstance(seat, str) or not seat.strip():
            problems.append(f"{path.name}: seat должен быть непустой строкой")
            continue
        seat_key = seat.strip().casefold()
        if seat_key in seats:
            duplicates.append(seat)
            problems.append(f"{path.name}: дубликат seat '{seat}' (уже есть в {seats[seat_key]})")
            continue
        seats[seat_key] = path.name
        if vote["inputs_sha256"] != inputs:
            problems.append(f"{path.name}: голос выдан не на текущие версии спеки и риск-плана")
            continue
        votes.append(vote)
    if duplicates:
        # Набор с повторяющимися судьями недействителен целиком: ни один голос не засчитывается.
        return [], problems
    return votes, problems


def run_check(name: str, cmd: list[str]) -> int:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    print(f"  {name}: код {result.returncode}")
    if result.returncode != 0:
        print((result.stdout + result.stderr)[-1500:], file=sys.stderr)
    return result.returncode


def blocked(reason: str) -> int:
    print(f"GATE: BLOCKED. {reason}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--votes-dir", type=Path, default=ROOT / ".ai-team" / "panel-votes")
    parser.add_argument("--out", type=Path, default=ROOT / "handoff" / "03-gate-proof.json")
    args = parser.parse_args()

    spec, risk_plan = ROOT / SPEC, ROOT / RISK_PLAN
    if not spec.is_file() or not risk_plan.is_file():
        return blocked("обязательные артефакты отсутствуют (спека или риск-план).")
    inputs = {"spec": sha256(spec), "risk_plan": sha256(risk_plan)}

    votes, problems = load_votes(args.votes_dir, inputs)
    for problem in problems:
        print(f"ГОЛОС ОТКЛОНЁН: {problem}", file=sys.stderr)
    positive = [v for v in votes if str(v["verdict"]).upper() in POSITIVE]
    print(f"Голосов принято: {len(votes)}, READY: {len(positive)} (каталог {args.votes_dir})")
    if len(votes) < MIN_VOTES:
        return blocked(f"нужно минимум {MIN_VOTES} валидных голоса, принято {len(votes)}.")
    if len(positive) < MIN_POSITIVE:
        return blocked(f"READY меньше {MIN_POSITIVE} из {len(votes)}: работа возвращается Coder.")

    print("Проверки:")
    checks = {
        "ruff_check": run_check("ruff check", [sys.executable, "-m", "ruff", "check", "."]),
        "pytest": run_check(
            "pytest", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        ),
    }
    if any(code != 0 for code in checks.values()):
        return blocked(f"проверки красные: {checks}.")

    proof = {
        "timestamp": datetime.now(UTC).isoformat(),
        "task_id": "LINK-42",
        "verdict": "PASS",
        "quorum": f"{len(positive)}/{len(votes)}",
        "inputs_sha256": inputs,
        "checks_exit_codes": checks,
        "votes": [
            {
                "seat": v["seat"],
                "verdict": v["verdict"],
                "finding": v["finding"],
                "origin": v.get("origin", "unknown"),
            }
            for v in votes
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(proof, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    origins = sorted({str(v.get("origin", "unknown")) for v in votes})
    print(f"GATE: PASS. Протокол: {args.out} (происхождение голосов: {', '.join(origins)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
