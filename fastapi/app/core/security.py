"""Безопасность ссылок: SSRF-защита целевых URL и генерация короткого кода.

Валидаторы живут в `app/schemas/validators.py` (схемы не импортируют `app.core`), а здесь
переэкспортируются для остального кода; доменные проверки — в `app/domain/value_objects.py`.
"""

import secrets

from app.domain.value_objects import CODE_ALPHABET, ShortCode, TargetUrl
from app.schemas.validators import (
    BLOCKED_NETWORKS,
    SecuritySSRFError,
    validate_target_url_security,
)

DEFAULT_CODE_LENGTH: int = 7


def validate_target_url(url: str) -> str:
    """Возвращает нормализованный URL или бросает `InvalidUrlError` (схема, SSRF, длина)."""
    return TargetUrl(url).value


def generate_short_code(length: int = DEFAULT_CODE_LENGTH) -> str:
    """Генерирует криптостойкий короткий код из `[A-Za-z0-9]` заданной длины."""
    return ShortCode("".join(secrets.choice(CODE_ALPHABET) for _ in range(length))).value


__all__ = [
    "BLOCKED_NETWORKS",
    "DEFAULT_CODE_LENGTH",
    "SecuritySSRFError",
    "generate_short_code",
    "validate_target_url",
    "validate_target_url_security",
]
