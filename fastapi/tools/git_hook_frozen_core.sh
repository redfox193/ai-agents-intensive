#!/usr/bin/env bash
set -e

FROZEN_FILES=("app/core/config.py" "app/core/security.py")

CHANGED=$(git diff --cached --name-only)

for file in $CHANGED; do
    for frozen in "${FROZEN_FILES[@]}"; do
        if [ "$file" == "$frozen" ]; then
            echo "🚨 ОШИБКА: Попытка коммита замороженного файла ядра: $file"
            echo "   Файлы ядра защищены от модификации агентами!"
            echo "   Требуется ручное подтверждение Архитектора."
            exit 1
        fi
    done
done

echo "✅ Проверка Frozen Core пройдена (защищенные файлы не затронуты)."
exit 0
