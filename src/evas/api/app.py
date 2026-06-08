"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from evas import __version__
from evas.api.ab_routes import router as ab_router
from evas.api.admin_routes import router as admin_router
from evas.api.ai_routes import router as ai_router
from evas.api.auth_routes import router as auth_router
from evas.api.billing_routes import router as billing_router
from evas.api.clips_routes import router as clips_router
from evas.api.human_reviews import router as human_reviews_router
from evas.api.portal_routes import router as portal_router
from evas.api.routes import router
from evas.api.sources_routes import router as sources_router
from evas.api.webhooks_routes import router as webhooks_router


def create_app() -> FastAPI:
    app = FastAPI(title="EVAS", version=__version__)
    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(human_reviews_router)
    app.include_router(webhooks_router)
    app.include_router(clips_router)
    app.include_router(billing_router)
    app.include_router(ab_router)
    app.include_router(portal_router)
    app.include_router(admin_router)
    app.include_router(sources_router)
    app.include_router(ai_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
