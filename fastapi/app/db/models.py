"""Реестр ORM-моделей: импорт ради регистрации таблиц в `Base.metadata`."""

from app.models.analytics import ClickEvent
from app.models.link import Link

LinkModel = Link

__all__ = ["ClickEvent", "Link", "LinkModel"]
