#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def validate_handoff(file_path: str) -> bool:
    path = Path(file_path)
    if not path.is_file():
        print(f"ОШИБКА: Файл пакета не найден: {file_path}", file=sys.stderr)
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"ОШИБКА: Невалидный JSON в {file_path}: {e}", file=sys.stderr)
        return False
    required_keys = ["task_id", "author_role", "artifacts", "decisions", "open_questions"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        print(f"ОШИБКА: В пакете отсутствуют обязательные секции: {missing}", file=sys.stderr)
        return False
    if not isinstance(data["decisions"], list) or len(data["decisions"]) == 0:
        print(
            "ОШИБКА: Секция 'decisions' обязана содержать список принятых решений", file=sys.stderr
        )
        return False
    if not isinstance(data["open_questions"], list) or len(data["open_questions"]) == 0:
        print(
            "ОШИБКА: Секция 'open_questions' обязана содержать список рисков/вопросов",
            file=sys.stderr,
        )
        return False
    print(f"УСПЕХ: Пакет {file_path} полностью соответствует контракту Structured Handoff!")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python3 scripts/validate_handoff.py <путь_к_json>", file=sys.stderr)
        sys.exit(2)
    success = validate_handoff(sys.argv[1])
    sys.exit(0 if success else 1)
