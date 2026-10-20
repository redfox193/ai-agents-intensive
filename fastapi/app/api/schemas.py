"""Фасад схем HTTP-слоя (путь `app/api/schemas.py` из скилов Дня 1): реальные — в `app/schemas/`."""

from app.schemas.link import LinkCreate, LinkCreated, LinkResponse

CreateLinkRequest = LinkCreate

__all__ = ["CreateLinkRequest", "LinkCreate", "LinkCreated", "LinkResponse"]
