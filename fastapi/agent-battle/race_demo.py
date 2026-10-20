"""Учебная демонстрация lost update счётчика переходов (не входит в `pytest`)."""

from __future__ import annotations

import asyncio

WORKERS = 20


class Counter:
    """Хранилище с одним числом: неатомарный и атомарный способы увеличить его."""

    def __init__(self) -> None:
        self.clicks = 0
        self._lock = asyncio.Lock()

    async def read_modify_write(self) -> None:
        snapshot = self.clicks
        await asyncio.sleep(0)
        self.clicks = snapshot + 1

    async def atomic_increment(self) -> None:
        async with self._lock:
            self.clicks += 1


async def run(method: str) -> int:
    counter = Counter()
    await asyncio.gather(*(getattr(counter, method)() for _ in range(WORKERS)))
    return counter.clicks


async def main() -> None:
    print(f"до фикса (чтение-изменение-запись): {await run('read_modify_write')} из {WORKERS}")
    print(f"после фикса (атомарный инкремент):  {await run('atomic_increment')} из {WORKERS}")


if __name__ == "__main__":
    asyncio.run(main())
