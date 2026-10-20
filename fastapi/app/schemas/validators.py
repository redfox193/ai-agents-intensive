"""Чистые валидаторы входных данных (SSRF-защита целевых URL).

Живут в слое `schemas`, чтобы схемы не импортировали `app.core`; `app/core/security.py`
переэкспортирует их для остального кода.
"""

import ipaddress
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()

BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SecuritySSRFError(ValueError):
    """Исключение при попытке обращения к приватным IP или локальным адресам."""

    pass


def validate_target_url_security(url_str: str) -> str:
    """
    Валидирует URL без блокирующего DNS-запроса:
    1. Проверяет допустимые протоколы (только http и https).
    2. Блокирует localhost и имена внутренних сервисов.
    3. Если хост является IP-адресом, проверяет его на принадлежность к приватным диапазонам.
    """
    parsed = urlparse(url_str.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise SecuritySSRFError(
            f"Запрещенный протокол: {parsed.scheme}. Разрешены только HTTP и HTTPS."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SecuritySSRFError("В URL отсутствует корректный хост.")

    lower_host = hostname.lower()
    if lower_host in ("localhost", "linkdb", "redis", "postgres", "testserver"):
        raise SecuritySSRFError(f"Запрещен внутренний хост: {lower_host}")

    # Проверка строковых IP-адресов
    try:
        ip_obj = ipaddress.ip_address(lower_host)
    except ValueError:
        # Доменное имя (например pytex.org) - не является прямым IP
        ip_obj = None

    if ip_obj is not None:
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
            raise SecuritySSRFError(f"Запрещен приватный IP-адрес: {lower_host}")
        for net in BLOCKED_NETWORKS:
            if ip_obj in net:
                raise SecuritySSRFError(
                    f"IP-адрес {lower_host} входит в заблокированную сеть {net}"
                )

    return url_str
