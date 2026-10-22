#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

FATAL_MARKERS = {
    "error",
    "fatal",
    "failed",
    "failure",
    "cancelled",
    "canceled",
    "aborted",
    "timeout",
    "timed_out",
    "interrupted",
    "session_error",
    "session.error",
}


def has_failure(event: object) -> bool:
    """Фатальны только session-level error-события верхнего уровня.

    Ошибки инструментов (is_error / state.status="error" внутри part) фатальными не
    считаются: модель может опечататься в oldString и успешно повторить вызов.
    """
    if not isinstance(event, dict):
        return False
    mapping = cast(dict[str, object], event)
    for key in ("event", "type", "status"):
        marker = str(mapping.get(key, "")).strip().lower()
        if marker in FATAL_MARKERS:
            return True
    error = mapping.get("error")
    return error not in (None, "", False, [], {})


def collect_text_events(source: Path) -> list[str]:
    parts: list[str] = []
    for number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            parsed: object = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SystemExit(f"СТОП: event line {number} is not JSON: {error}") from error
        if not isinstance(parsed, dict):
            raise SystemExit(f"СТОП: event line {number} is not an object")
        event = cast(dict[str, object], parsed)
        if has_failure(event):
            raise SystemExit(f"СТОП: event line {number} contains session-level failure")
        if event.get("type") == "text":
            part = event.get("part")
            if isinstance(part, dict):
                part_mapping = cast(dict[str, object], part)
                content = part_mapping.get("text")
                if isinstance(content, str) and content.strip():
                    parts.append(content)
    if not parts:
        raise SystemExit("СТОП: no text events found")
    return parts


def find_last_json_object(text: str) -> dict[str, object] | None:
    """Последний валидный JSON object в тексте; нарратив вокруг JSON допустим."""
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


def extract_object(parts: list[str]) -> dict[str, object]:
    """Последний валидный JSON object из последнего text-события, которое его содержит."""
    for text in reversed(parts):
        value = find_last_json_object(text)
        if value is not None:
            return value
    raise SystemExit("СТОП: no text event contains a JSON object")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("events", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = extract_object(collect_text_events(args.events))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"EXTRACTED {args.output}")


if __name__ == "__main__":
    main()
