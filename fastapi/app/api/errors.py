from typing import NoReturn

from fastapi import HTTPException, status

from app.services.link import (
    LinkExpiredError,
    LinkInactiveError,
    LinkNotFoundError,
    LinkServiceError,
    ShortCodeConflictError,
)


def raise_flat(exc: LinkServiceError) -> NoReturn:
    """Плоские маршруты (`/links`, `/{code}`): англоязычные `detail` из спеки LINK-42."""
    if isinstance(exc, LinkNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found") from exc
    if isinstance(exc, LinkInactiveError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link disabled") from exc
    if isinstance(exc, LinkExpiredError):
        raise HTTPException(status.HTTP_410_GONE, detail="Link expired") from exc
    if isinstance(exc, ShortCodeConflictError):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Short code already taken") from exc
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
