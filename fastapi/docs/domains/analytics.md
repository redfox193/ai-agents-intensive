# Доменная спецификация: Analytics (Аналитика кликов)

## Назначение
Сбор агрегированных метрик переходов по коротким ссылкам: распределение по странам, браузерам и часам суток.

## Компоненты
- `app/schemas/analytics.py` — `ClickEventResponse`, `LinkDetailedAnalytics`.
- `app/services/analytics.py` — `AnalyticsService` (`record_click`, `get_link_detailed_analytics`).
- `app/api/v1/endpoints/analytics.py` — `GET /api/v1/analytics/{short_code}`.

## Инварианты
1. Агрегация выполняется асинхронно, не блокируя редирект ссылок.
2. Слой аналитики зависит только от схем и ядра.
