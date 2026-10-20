from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, synonym
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import Base, TimestampMixin


class Link(Base, TimestampMixin):
    """Единая ORM-модель короткой ссылки (таблица `links`) для всех слоёв и всех дней.

    Имена колонок — `target_url`, `clicks`, `disabled`. Синонимы `code`, `original_url`,
    `clicks_count` и гибрид `is_active` сохраняют прежние имена Дней 1-3.
    """

    __table_args__ = (Index("ix_links_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    code = synonym("short_code")
    original_url = synonym("target_url")
    clicks_count = synonym("clicks")

    @hybrid_property
    def is_active(self) -> bool:
        """Ссылка включена (обратный флаг к `disabled`)."""
        return not self.disabled

    @is_active.inplace.setter
    def _is_active_setter(self, value: bool) -> None:
        self.disabled = not value

    @is_active.inplace.expression
    @classmethod
    def _is_active_expression(cls) -> ColumnElement[bool]:
        return cls.disabled.is_(False)

    @property
    def is_expired(self) -> bool:
        """Проверка истечения срока действия ссылки."""
        if self.expires_at is None:
            return False
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            # SQLite возвращает наивное время: считаем его UTC
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) > expires_at

    @property
    def status(self) -> str:
        """Текущий статус: `disabled`, `expired` или `active`."""
        if self.disabled:
            return "disabled"
        return "expired" if self.is_expired else "active"
