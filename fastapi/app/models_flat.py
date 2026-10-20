"""Плоский фасад моделей (прежний `app/models.py` Дня 2): `Base` и `Link` одним импортом."""

from app.db.base import Base
from app.models.link import Link

__all__ = ["Base", "Link"]
