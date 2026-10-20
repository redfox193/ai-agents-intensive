#!/usr/bin/env python3

SUGGESTIONS = {
    "app.services -> app.api": (
        "ВЫНОС В ОБЩИЙ СЕРВИС: Функция или схема, импортируемая из роутера, "
        "должна быть перемещена в app/services/ или app/schemas/."
    ),
    "app.schemas -> app.services": (
        "ИНВЕРСИЯ ЗАВИСИМОСТИ: Схема данных не может знать о бизнес-логике. "
        "Перенесите валидацию в слой сервиса или используйте декларативные Field(gt=0)."
    ),
    "app.core -> app.api": (
        "РАЗРЫВ СВЯЗИ ЯДРА: Модуль ядра должен оперировать только абстрактными протоколами. "
        "Удалите импорт роутера из core/."
    ),
    "fastapi in services": (
        "ТРАНСПОРТНАЯ ИЗОЛЯЦИЯ: Замените HTTPException на доменное исключение "
        "(например, InsufficientFundsError) и транслируйте его в HTTP-статус внутри api/billing.py."
    ),
}


def analyze_and_suggest():
    print("=== АНАЛИЗАТОР РЕФАКТОРИНГА АРХИТЕКТУРНЫХ СЛОЕВ ===")
    print("Рекомендации по устранению типовых нарушений:")
    for pattern, advice in SUGGESTIONS.items():
        print(f"\n[Паттерн нарушения]: {pattern}")
        print(f"-> РЕКОМЕНДАЦИЯ: {advice}")


if __name__ == "__main__":
    analyze_and_suggest()
