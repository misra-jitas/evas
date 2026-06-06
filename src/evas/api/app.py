"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from evas import __version__
from evas.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="EVAS", version=__version__)
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
