"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from evas import __version__
from evas.api.auth_routes import router as auth_router
from evas.api.human_reviews import router as human_reviews_router
from evas.api.routes import router
from evas.api.webhooks_routes import router as webhooks_router


def create_app() -> FastAPI:
    app = FastAPI(title="EVAS", version=__version__)
    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(human_reviews_router)
    app.include_router(webhooks_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
