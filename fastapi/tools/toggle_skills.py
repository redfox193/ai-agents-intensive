#!/usr/bin/env python3
"""Утилита переключения режима работы: с процедурными скилами или без них (vibe-coding demo)."""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
STASH_DIR = Path.home() / ".cache" / "pytex-skills-stash"


def get_tracked_skills():
    res = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", ".agents/skills"],
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def disable_skills():
    if not SKILLS_DIR.exists():
        print("⚠️  .agents/skills не найден или уже отключен.")
        return 0
    # Mark tracked files assume-unchanged so git status stays clean
    tracked = get_tracked_skills()
    if tracked:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "update-index", "--assume-unchanged", *tracked],
            check=True,
        )
    STASH_DIR.parent.mkdir(parents=True, exist_ok=True)
    if STASH_DIR.exists():
        shutil.rmtree(STASH_DIR)
    shutil.move(str(SKILLS_DIR), str(STASH_DIR))
    print(f"🔒 [SKILLS DISABLED] Скилы временно перемещены в {STASH_DIR}.")
    print("   Git не считает файлы удалёнными (--assume-unchanged).")
    print("   Агент теперь работает в «диком» режиме вайб-кодинга (0 скилов в проекте).")
    return 0


def enable_skills():
    if not STASH_DIR.exists():
        if SKILLS_DIR.exists():
            print("✅ .agents/skills уже активен.")
            return 0
        print("⚠️  Резервная копия скилов не найдена в stash.")
        return 1
    if SKILLS_DIR.exists():
        shutil.rmtree(SKILLS_DIR)
    shutil.move(str(STASH_DIR), str(SKILLS_DIR))
    tracked = get_tracked_skills()
    if tracked:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "update-index", "--no-assume-unchanged", *tracked],
            check=True,
        )
    count = len(list(SKILLS_DIR.iterdir()))
    print(f"🔓 [SKILLS ENABLED] Скилы возвращены в репозиторий ({count} процедур доступно).")
    print("   Агент снова вооружен процедурными контрактами и L1-L3 инструкциями.")
    return 0


def status_skills():
    if SKILLS_DIR.exists():
        count = len(list(SKILLS_DIR.iterdir()))
        print(f"🟢 Скилы АКТИВНЫ (.agents/skills, {count} процедур)")
    else:
        print(f"🔴 Скилы ОТКЛЮЧЕНЫ (находятся в {STASH_DIR})")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "--status"
    if cmd in ("--disable", "disable", "off"):
        sys.exit(disable_skills())
    elif cmd in ("--enable", "enable", "on"):
        sys.exit(enable_skills())
    elif cmd in ("--status", "status"):
        sys.exit(status_skills())
    else:
        print("Использование: python3 tools/toggle_skills.py [--disable | --enable | --status]")
        sys.exit(1)
