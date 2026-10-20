#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

VALID_TRANSITIONS = {
    "DISCUSS": ["PLAN"],
    "PLAN": ["EXECUTE"],
    "EXECUTE": ["VERIFY"],
    "VERIFY": ["EXECUTE", "PLAN", "DONE"],
    "DONE": ["DISCUSS"],
}


def transition(new_state: str):
    root = Path.cwd()
    state_file = root / ".planning" / "STATE.md"
    if not state_file.exists():
        print("❌ .planning/STATE.md не найден!")
        return 1

    content = state_file.read_text(encoding="utf-8")
    m = re.search(r"Active State:(?:\*\*)?\s*(\w+)", content)
    curr = m.group(1) if m else "UNKNOWN"

    allowed = VALID_TRANSITIONS.get(curr, [])
    if new_state not in allowed:
        print(f"❌ НЕДОПУСТИМЫЙ ПЕРЕХОД FSM: {curr} -> {new_state}!")
        print(f"   Разрешенные переходы из {curr}: {', '.join(allowed)}")
        return 1

    updated = re.sub(r"(Active State:(?:\*\*)?\s*)\w+", rf"\g<1>{new_state}", content)
    state_file.write_text(updated, encoding="utf-8")
    print(f"✅ УСПЕШНЫЙ ПЕРЕХОД FSM: {curr} -> {new_state}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Контроллер переходов конечного автомата GSD")
    parser.add_argument("state", choices=["DISCUSS", "PLAN", "EXECUTE", "VERIFY", "DONE"])
    args = parser.parse_args()
    sys.exit(transition(args.state))


if __name__ == "__main__":
    main()
