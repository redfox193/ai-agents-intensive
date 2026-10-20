#!/usr/bin/env bash
set -e

WAVE_NUM=${1:-1}
WAVE_NAME=${2:-"Schemas"}

echo "================================================================="
echo "   ЗАПУСК ИЗОЛИРОВАННОЙ ВОЛНЫ GSD: ВОЛНА $WAVE_NUM ($WAVE_NAME)"
echo "   КОНТЕКСТНОЕ ОКНО: СВЕЖИЕ 200k ТОКЕНОВ (ИСТОРИЯ ОЧИЩЕНА)"
echo "================================================================="

# 1. Проверяем валидность состояния FSM
python3 tools/plan_checker.py

# 2. Выполняем точечный Scoped Retrieval
python3 tools/scoped_retrieval.py --target "app.schemas.billing"

# 3. Фиксируем чекпоинт
echo "Волна $WAVE_NUM готова к выполнению сабагентом."
