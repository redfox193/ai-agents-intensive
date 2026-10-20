from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.billing import router as billing_router
from app.api.deps import ServiceDep
from app.api.errors import raise_flat
from app.api.routes import router as links_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.db.session import engine
from app.services.link import LinkServiceError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Управление жизненным циклом приложения при старте и завершении."""
    setup_logging()
    logger.info("app_starting", project_name=settings.PROJECT_NAME, env=settings.APP_ENV)
    yield
    logger.info("app_stopping")
    await engine.dispose()
    logger.info("db_pool_disposed")


async def health_check() -> dict[str, str | bool]:
    """Healthcheck эндпоинт проверки жизнеспособности сервиса."""
    return {"status": "ok", "monolith": True}


async def redirect_to_target(short_code: str, service: ServiceDep) -> RedirectResponse:
    """Редирект `GET /{code}`: 307 для активной ссылки (клик учитывается), 404 для отключённой."""
    try:
        url = await service.resolve_link(short_code)
    except LinkServiceError as exc:
        raise_flat(exc)
    return RedirectResponse(url=url, status_code=307)


def create_application() -> FastAPI:
    """Фабрика создания экземпляра приложения FastAPI (монолит: links + analytics + billing)."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="2.4.0",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(links_router)
    app.include_router(billing_router)

    app.add_api_route("/health", health_check, status_code=status.HTTP_200_OK, tags=["system"])
    # Перехватывающий маршрут регистрируется последним, чтобы не заслонять остальные.
    app.add_api_route("/{short_code}", redirect_to_target, methods=["GET"], tags=["links"])

    return app


app = create_application()
