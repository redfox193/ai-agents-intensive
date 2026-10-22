#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path


def fingerprint(root: Path, protected_only: bool) -> str:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    listed = {part.decode("utf-8") for part in result.stdout.split(b"\0") if part}
    protected = {
        "workshop.md",
        ".env",
        "pyproject.toml",
        "uv.lock",
        "AGENTS.md",
        "CLAUDE.md",
        "docker-compose.yml",
    }
    for directory in (".agents", ".opencode"):
        base = root / directory
        if base.is_dir():
            protected.update(
                str(path.relative_to(root)) for path in base.rglob("*") if path.is_file()
            )
    relatives = protected if protected_only else listed | protected
    digest = hashlib.sha256()
    for relative in sorted(relatives):
        if relative == ".ai-team" or relative.startswith(".ai-team/"):
            continue
        path = root / relative
        if not path.is_file():
            continue
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", type=Path)
    group.add_argument("--compare", type=Path)
    parser.add_argument("--protected-only", action="store_true")
    args = parser.parse_args()
    current = fingerprint(Path.cwd(), args.protected_only)
    if args.write is not None:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(current + "\n", encoding="utf-8")
        print(f"FINGERPRINT {current}")
        return
    before = args.compare.read_text(encoding="utf-8").strip()
    if before != current:
        raise SystemExit(f"СТОП: worktree изменён read-only ролью: {before} != {current}")
    print(f"WORKTREE_UNCHANGED {current}")


if __name__ == "__main__":
    main()
