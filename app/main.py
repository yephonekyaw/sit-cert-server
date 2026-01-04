from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.utils.logging import get_logger
from app.routers import main_router, webhook_router
from app.utils.errors import setup_error_handlers
from app.middlewares import (
    RequestIDMiddleware,
    DevSecurityMiddleware,
    ProdSecurityMiddleware,
    AuthMiddleware,
)

# Initialize the logger
logger = get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("SIT Cert is starting up...")
    yield
    logger.info("SIT Cert is shutting down...")


def create_application() -> FastAPI:
    """Initialize the FastAPI application with settings and lifespan events."""
    application = FastAPI(
        title=settings.NAME, version=settings.VERSION, lifespan=lifespan
    )

    # Setup error handlers
    setup_error_handlers(application)

    # Add CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "authorization"],
    )

    # Add custom middlewares
    # application.add_middleware(
    #     DevSecurityMiddleware
    #     if settings.ENVIRONMENT == "development"
    #     else ProdSecurityMiddleware
    # )
    application.add_middleware(DevSecurityMiddleware)
    application.add_middleware(AuthMiddleware)
    application.add_middleware(RequestIDMiddleware)

    # Routers
    application.include_router(main_router, prefix=settings.API_PREFIX, tags=["APIs"])
    application.include_router(
        webhook_router, prefix=settings.WEBHOOK_PREFIX, tags=["Webhooks"]
    )

    return application


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None,
        log_level=None,
    )
