#!/usr/bin/env bash
set -e

SNAPSHOT=${1:-"snap-6"}

echo "=== ВОССТАНОВЛЕНИЕ КОНТРОЛЬНОГО СРЕЗА: $SNAPSHOT ==="

case $SNAPSHOT in
  "snap-0")
    echo "Откат к исходному состоянию: единое приложение и 9 скилов Дней 1-2..."
    git checkout snap-0 2>/dev/null || git checkout main
    ;;
  "snap-1")
    echo "Развертывание Базы знаний (docs/INDEX.md)..."
    python3 tools/verify_kb_sync.py
    ;;
  "snap-2")
    echo "Граф зависимостей монолита: проверка ацикличности..."
    python3 tools/build_dependency_graph.py --check-cycles
    ;;
  "snap-3")
    echo "Требования EARS и конвейер GSD (Волна 1: Schemas)..."
    pytest tests/unit/test_ears_requirements.py -q
    ;;
  "snap-4")
    echo "Линтер границ архитектурных слоёв..."
    python3 tools/verify_architecture_layers.py
    ;;
  "snap-5")
    echo "Blast Radius Guard: бюджет изменений и замороженное ядро..."
    python3 tools/verify_blast_radius.py
    ;;
  "snap-6")
    echo "Полный срез: 15 скилов, все верификаторы и Techlead Gate..."
    python3 tools/verify_techlead_gate.py
    ;;
  *)
    echo "Неизвестный срез: $SNAPSHOT. Доступные: snap-0 … snap-6"
    exit 1
    ;;
esac

echo "✅ Срез $SNAPSHOT успешно применен!"
