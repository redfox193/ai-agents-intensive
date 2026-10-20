# Спека: POST /links/{short_code}/enable

1. Что строим: эндпоинт включения ранее отключённой ссылки.
2. Рамки: правим app/api/routes.py и app/repositories/link.py, тесты в tests/. Не трогаем схему БД.
3. Вход: short_code из пути. Несуществующий код даёт 404.
4. Выход: 200 и {"short_code": ..., "disabled": false}.
5. Критерий готовности: characterization зелёный, новый тест на enable зелёный.
6. Запрещено: логировать target_url, ослаблять гейты, менять AGENTS.md.
7. Контрольные точки: spec на диске, diff, лог гейтов, вердикт ревьюера.
