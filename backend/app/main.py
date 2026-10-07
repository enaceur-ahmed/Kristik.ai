"""
AI Data Engineering Copilot — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import Base, engine
from app.core.logging_config import setup_logging, get_logger
from app.api.datasets import router as datasets_router
from app.api.analysis import router as analysis_router
from app.api.benchmark_routes import router as benchmark_router
from app.api.chat import router as chat_router

setup_logging("DEBUG" if settings.DEBUG else "INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup."""
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    _warn_incomplete_llm_config()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready.")
    yield
    logger.info("Shutting down.")


def _warn_incomplete_llm_config() -> None:
    """Warn at startup when a real provider is selected but not fully configured."""
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "demo":
        return
    missing = [
        name
        for name, value in (
            ("LLM_API_KEY", settings.LLM_API_KEY),
            ("LLM_MODEL", settings.LLM_MODEL),
        )
        if not value
    ]
    if missing:
        logger.warning(
            "LLM_PROVIDER is '%s' but %s %s empty — Demo Mode will be used "
            "for recommendations. Set the missing variable(s) in .env to use "
            "the real LLM.",
            settings.LLM_PROVIDER,
            " and ".join(missing),
            "is/are",
        )


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered Data Engineering pipeline automation tool.",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(datasets_router)
app.include_router(analysis_router)
app.include_router(benchmark_router)
app.include_router(chat_router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "demo_mode": (settings.LLM_PROVIDER.lower().strip() == "demo"
                      or not bool(settings.LLM_API_KEY)),
    }
