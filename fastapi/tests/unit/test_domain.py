from datetime import UTC, datetime, timedelta

import pytest

from app.domain.errors import InvalidShortCodeError, InvalidUrlError
from app.domain.link import Link, LinkStatus
from app.domain.value_objects import ShortCode, TargetUrl

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_link(**overrides) -> Link:
    fields = {
        "short_code": ShortCode("abcd1234"),
        "target_url": TargetUrl("https://example.com"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Link(**fields)


def test_target_url_is_normalized_and_validated() -> None:
    assert TargetUrl("  https://example.com/a  ").value == "https://example.com/a"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com",
        "https://",
        "https://user:pass@example.com",
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "https://example.com/" + "a" * 2100,
    ],
)
def test_target_url_rejects_unsafe_values(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        TargetUrl(url)


@pytest.mark.parametrize("code", ["abc", "a" * 17, "bad code", "кириллица"])
def test_short_code_rejects_invalid_values(code: str) -> None:
    with pytest.raises(InvalidShortCodeError):
        ShortCode(code)


def test_link_status_transitions() -> None:
    assert make_link().status(NOW) is LinkStatus.ACTIVE
    assert make_link(disabled=True).status(NOW) is LinkStatus.DISABLED
    expired = make_link(expires_at=NOW - timedelta(seconds=1))
    assert expired.status(NOW) is LinkStatus.EXPIRED
    assert expired.is_active(NOW) is False


def test_link_is_immutable_value_with_click_and_disable() -> None:
    link = make_link()
    assert link.with_click().clicks == 1
    assert link.clicks == 0
    assert link.disable().disabled is True
    assert link.disabled is False
