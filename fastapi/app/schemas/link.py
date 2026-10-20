from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class LinkBase(BaseModel):
    """Базовые поля ссылки: адрес назначения — `original_url` (или алиасы `target_url`, `url`)."""

    original_url: str = Field(
        ...,
        validation_alias=AliasChoices("original_url", "target_url", "url"),
        description="Оригинальный длинный URL",
    )

    @field_validator("original_url")
    def validate_url_security(cls, v: str) -> str:
        from app.schemas.validators import validate_target_url_security

        return validate_target_url_security(v)

    custom_code: str | None = Field(
        None,
        min_length=3,
        max_length=16,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Пользовательский короткий код (опционально)",
    )
    ttl_seconds: int | None = Field(
        None,
        gt=0,
        le=31536000,
        description="Время жизни ссылки в секундах (до 1 года)",
    )


class LinkCreate(LinkBase):
    """Схема создания новой ссылки."""

    pass


class LinkResponse(BaseModel):
    """Полный ответ о ссылке: имена полей Дней 1-3 (`target_url`/`original_url`, `clicks`/...)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    short_code: str
    original_url: str
    target_url: str
    short_url: str = ""
    clicks_count: int
    clicks: int
    is_active: bool
    disabled: bool
    status: str
    created_at: datetime
    expires_at: datetime | None


class LinkCreated(BaseModel):
    """Контракт `specs/LINK-42-enable-link.md`: код, адрес назначения, флаг отключения."""

    model_config = ConfigDict(from_attributes=True)

    short_code: str
    target_url: str
    disabled: bool


class LinkStats(BaseModel):
    """Статистика переходов по ссылке (`GET /api/v1/links/{code}/stats`)."""

    model_config = ConfigDict(from_attributes=True)

    short_code: str
    original_url: str
    target_url: str
    clicks_count: int
    clicks: int
    is_active: bool
    disabled: bool
    is_expired: bool
    status: str
    created_at: datetime
    expires_at: datetime | None


class LinkBulkCreateItem(BaseModel):
    """Элемент пакета для массового создания."""

    original_url: str
    custom_code: str | None = None
    ttl_seconds: int | None = None


class LinkBulkCreateRequest(BaseModel):
    """Запрос на пакетное создание ссылок."""

    items: list[LinkBulkCreateItem] = Field(..., min_length=1, max_length=100)


class LinkBulkCreateResponse(BaseModel):
    """Ответ на пакетное создание ссылок."""

    created_count: int
    links: list[LinkResponse]


LinkRead = LinkResponse
