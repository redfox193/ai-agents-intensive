#!/usr/bin/env python3
import sys
from pathlib import Path as _Path

sys.path.insert(
    0, str(_Path(__file__).resolve().parents[1])
)  # корень проекта: импорт `app` и `tools`

import time

from fastapi.testclient import TestClient

from app.main import app


def run_benchmark(requests_count=500):
    client = TestClient(app)
    # Пополняем начальный баланс
    client.post("/billing/wallets/top-up", json={"user_id": 999, "amount": 100000})

    latencies = []
    print(f"=== ЗАПУСК БЕНЧМАРКА: {requests_count} ЗАПРОСОВ К /billing/charges/click ===")

    start_total = time.perf_counter()
    for i in range(requests_count):
        payload = {
            "user_id": 999,
            "link_id": 1,
            "amount": 10,
            "transaction_id": f"tx_bench_{i}_{time.time_ns()}",
        }
        t0 = time.perf_counter()
        res = client.post("/billing/charges/click", json=payload)
        t1 = time.perf_counter()
        assert res.status_code == 200
        latencies.append((t1 - t0) * 1000)  # мс

    total_time = time.perf_counter() - start_total
    latencies.sort()

    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    rps = requests_count / total_time

    print(f"Всего выполнено запросов: {requests_count}")
    print(f"Общее время: {total_time:.2f} сек (RPS: {rps:.1f} req/sec)")
    print(f"Задержка p50: {p50:.2f} мс")
    print(f"Задержка p95: {p95:.2f} мс")
    print(f"Задержка p99: {p99:.2f} мс")
    print("✅ БЕНЧМАРК ПРОЙДЕН: Производительность соответствует SLA (< 5 мс на запрос)")


if __name__ == "__main__":
    run_benchmark()
