import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory, run_migrations
from app.jobs.handlers import default_handlers
from app.jobs.runner import JobRunner
from app.routers import analyze, health, jobs, videos

logger = logging.getLogger("lets.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        run_migrations(settings.database_url)
        engine = make_engine(settings.database_url)
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        runner = JobRunner(
            app.state.session_factory,
            default_handlers(settings.stub_job_steps, settings.stub_job_step_ms),
        )
        if stale := runner.recover():
            logger.warning("Marked %d interrupted job(s) as failed", stale)
        app.state.jobs = runner
        logger.info("LETS API %s started (env=%s)", __version__, settings.env)
        yield
        runner.shutdown()
        engine.dispose()

    app = FastAPI(
        title="LETS Video Analyzer API",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.include_router(health.router, prefix="/v1")
    app.include_router(videos.router, prefix="/v1")
    app.include_router(analyze.router, prefix="/v1")
    app.include_router(jobs.router, prefix="/v1")
    return app


app = create_app()
