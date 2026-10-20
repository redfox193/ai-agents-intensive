from tools.verify_kb_sync import verify_kb


def test_kb_sync_passes_on_valid_repo():
    """Тест: на актуальном репозитории verify_kb возвращает 0 (OK)."""
    assert verify_kb() == 0


def test_kb_sync_fails_when_index_exceeds_size(tmp_path, monkeypatch):
    """Тест: если docs/INDEX.md превышает 100 строк, проверка падает."""
    monkeypatch.chdir(tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    index_file = docs_dir / "INDEX.md"

    # Генерируем 105 строк
    index_file.write_text("\n".join([f"Line {i}" for i in range(105)]), encoding="utf-8")
    assert verify_kb() == 1


def test_kb_sync_detects_missing_file_reference(tmp_path, monkeypatch):
    """Тест: если в docs/INDEX.md упомянут несуществующий файл, ловится FILE_MISSING."""
    monkeypatch.chdir(tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    index_file = docs_dir / "INDEX.md"
    index_file.write_text("# Index\n`app/schemas/non_existent.py`\n", encoding="utf-8")
    assert verify_kb() == 1
