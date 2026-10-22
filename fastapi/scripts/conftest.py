"""Общие фикстуры контрактных тестов скриптов Панели: временная копия эталонного пакета.

Тесты работают только на копии в `tmp_path`: корень проекта передаётся в функции скриптов
параметром `root`, основное дерево не меняется.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_proof as gp  # noqa: E402  # каталог scripts должен попасть в sys.path до импорта

REPO_ROOT = SCRIPTS_DIR.parent
REFERENCE_PATHS: tuple[str, ...] = (
    "specs/LINK-42-enable-link.md",
    "docs/risk-plan-LINK-42.md",
    "docs/gate-rubric.md",
    ".ai-team",
    "app",
    "tests",
    "alembic",
    "pyproject.toml",
)
QUESTIONS_MARK = "## Вопросы коллегам (к следующему раунду)"


@dataclass
class PanelKit:
    """Копия эталонного пакета и помощники для точечных правок в тестах."""

    root: Path

    @property
    def team(self) -> Path:
        """Каталог `.ai-team` копии."""
        return self.root / ".ai-team"

    @property
    def panel(self) -> Path:
        """Каталог `.ai-team/panel` копии."""
        return self.team / "panel"

    def path(self, rel: str) -> Path:
        """Путь внутри копии."""
        return self.root / rel

    def read(self, rel: str) -> str:
        """Содержимое файла копии."""
        return self.path(rel).read_text(encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        """Записывает файл копии."""
        target = self.path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def replace(self, rel: str, old: str, new: str) -> None:
        """Заменяет ровно одно вхождение: правка обязана попасть в цель."""
        text = self.read(rel)
        assert text.count(old) == 1, f"{rel}: фрагмент {old!r} встречается {text.count(old)} раз"
        self.write(rel, text.replace(old, new))

    def delete(self, rel: str) -> None:
        """Удаляет файл или каталог копии."""
        target = self.path(rel)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    def add_line(self, rel: str, line: str) -> None:
        """Добавляет строку перед секцией вопросов (для файлов D) либо в конец файла."""
        text = self.read(rel)
        if QUESTIONS_MARK in text:
            self.write(rel, text.replace(QUESTIONS_MARK, f"{line}\n{QUESTIONS_MARK}"))
        else:
            self.write(rel, text.rstrip("\n") + f"\n{line}\n")

    def check(self) -> gp.PanelResult:
        """Проверка пакета без записи файлов."""
        return gp.check_panel(self.team, self.root)

    def run_verify(self) -> int:
        """Режим verify с записью итогов; возвращает код выхода."""
        return gp.main(
            [str(self.team), str(self.root / "handoff" / "03-gate-proof.json")], self.root
        )

    def rechain(self) -> str:
        """Пересобирает реестр, freeze и подставляет digest в C1; возвращает digest."""
        gp.write_ledger(self.team, self.root)
        digest = gp.write_freeze(self.team, self.root)
        for seat in gp.SEATS:
            rel = f".ai-team/panel/c1/{seat}.md"
            text = re.sub(
                r"^FREEZE_SHA256: .*$", f"FREEZE_SHA256: {digest}", self.read(rel), flags=re.M
            )
            self.write(rel, text)
        return digest

    def repin(self) -> None:
        """Пересобирает manifest после смены входов и подставляет его sha256 в файлы судей."""
        pass_id = str(json.loads(self.read(".ai-team/panel/manifest.json"))["pass_id"])
        manifest_sha = gp.write_manifest(self.team, self.root, pass_id=pass_id)
        for path in self.panel.glob("*/judge-*.md"):
            text = path.read_text(encoding="utf-8")
            path.write_text(
                re.sub(
                    r"^PROCEDURE_ACCEPTED: .*$",
                    f"PROCEDURE_ACCEPTED: {manifest_sha}",
                    text,
                    flags=re.M,
                ),
                encoding="utf-8",
            )

    def set_c1_verdicts(self, votes: dict[str, str], objection: str | None = None) -> None:
        """Выставляет VERDICT в файлах C1; у REJECT добавляет OBJECTION, если он задан."""
        for seat, vote in votes.items():
            rel = f".ai-team/panel/c1/{seat}.md"
            text = re.sub(r"^VERDICT: .*$", f"VERDICT: {vote}", self.read(rel), flags=re.M)
            if vote == "REJECT" and objection is not None:
                text = text.replace("FALLBACK_CONSENT", f"OBJECTION: {objection}\nFALLBACK_CONSENT")
            self.write(rel, text)


@pytest.fixture
def kit(tmp_path: Path) -> PanelKit:
    """Временная копия эталонного пакета (спека, риск-план, рубрика, `.ai-team`, код продукта)."""
    root = tmp_path / "project"
    for rel in REFERENCE_PATHS:
        source = REPO_ROOT / rel
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, target)
    return PanelKit(root)
