# Issue: регрессия enable после Дня 2

Симптом: POST /links/{code}/enable после disable возвращает 404.
На Дне 2 после мержа было 200: это регрессия, а не первая поломка.
Ожидание: 200 и {"disabled": false}.
Радиус: app/api/routes.py, app/repositories/link.py, tests/flat_api/test_enable.py.
Вне радиуса: схема БД, characterization, docs/archive.
