"""Aplicación FastAPI del backend del prototipo."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.errors import PipelineError
from app.db.database import Base, engine
from app.models.video import Video  # noqa: F401 - registra el modelo antes de create_all

app = FastAPI(title="YouTube Didactic Material API", version="0.1.0")
app.include_router(router)


@app.exception_handler(PipelineError)
async def handle_pipeline_error(_request: Request, error: PipelineError) -> JSONResponse:
    """Keep domain errors JSON-shaped even when raised outside a route try/except."""
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"code": error.code, "message": str(error)}},
    )


@app.on_event("startup")
def initialise_local_metadata() -> None:
    """Crea la tabla SQLite local; no hay dependencias de bases remotas."""
    Base.metadata.create_all(bind=engine)
