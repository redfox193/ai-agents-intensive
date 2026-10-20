"""Плоский фасад сервиса домена Links (реальные определения — в `app/services/link.py`)."""

from app.services.link import (
    LinkExpiredError,
    LinkInactiveError,
    LinkNotFoundError,
    LinkService,
    LinkServiceError,
    ShortCodeConflictError,
)

__all__ = [
    "LinkExpiredError",
    "LinkInactiveError",
    "LinkNotFoundError",
    "LinkService",
    "LinkServiceError",
    "ShortCodeConflictError",
]
