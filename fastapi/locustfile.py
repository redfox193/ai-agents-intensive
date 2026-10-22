from __future__ import annotations

import random
import string

from locust import HttpUser, between, task

# Сценарий FastAPI-трека: смесь записи и чтения.


def _random_url() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    return f"https://example.com/{suffix}"


class LinkUser(HttpUser):
    wait_time = between(0.0, 0.05)

    def on_start(self) -> None:
        self._codes: list[str] = []

    @task(3)
    def create_link(self) -> None:
        resp = self.client.post("/links", json={"url": _random_url()})
        if resp.status_code == 201:
            code = resp.json().get("short_code")
            if code and len(self._codes) < 200:
                self._codes.append(code)

    @task(6)
    def get_link(self) -> None:
        if not self._codes:
            return
        code = random.choice(self._codes)
        self.client.get(f"/links/{code}", name="/links/{code}")

    @task(1)
    def list_links(self) -> None:
        self.client.get("/links")
