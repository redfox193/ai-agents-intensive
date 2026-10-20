#!/usr/bin/env bash
set -e

echo "=== ВОСПРОИЗВЕДЕНИЕ КОНТУРА ДНЯ 3: МОНОЛИТ, GSD И АРХИТЕКТУРНЫЕ СЛОИ ==="

# 1. Проверка окружения
python3 -c "import fastapi, pydantic, pytest; print('Базовые зависимости установлены')"

# 2. Проверка базы знаний
python3 tools/verify_kb_sync.py

# 3. Проверка топологии графа
python3 tools/build_dependency_graph.py --check-cycles

# 4. Проверка границ слоев
python3 tools/verify_architecture_layers.py

# 5. Проверка бюджета Blast Radius
python3 tools/verify_blast_radius.py

# 6. Прогон тестов и Techlead Gate
python3 tools/verify_techlead_gate.py

echo "=== КОНТУР ДНЯ 3 УСПЕШНО РАЗВЕРНУТ И ВЕРИФИЦИРОВАН ==="
