"""Aplicación FastAPI del backend del prototipo."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes import router
from app.core.errors import PipelineError
from app.db.database import Base, engine
from app.models.material import DidacticMaterial  # noqa: F401 - registra el modelo antes de create_all
from app.models.video import Video  # noqa: F401 - registra el modelo antes de create_all

app = FastAPI(title="YouTube Didactic Material API", version="0.1.0")
app.include_router(router)
WEB_DIRECTORY = Path(__file__).resolve().parent / "web"
app.mount("/ui", StaticFiles(directory=WEB_DIRECTORY, html=True), name="ui")


@app.get("/", include_in_schema=False)
def open_visual_interface() -> RedirectResponse:
    """Send local users to the visual prototype rather than a bare JSON response."""
    return RedirectResponse(url="/ui/")


@app.exception_handler(PipelineError)
async def handle_pipeline_error(_request: Request, error: PipelineError) -> JSONResponse:
    """Keep domain errors JSON-shaped even when raised outside a route try/except."""
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"code": error.code, "message": str(error)}},
    )


@app.on_event("startup")
def initialise_local_metadata() -> None:
    """Crea tablas y añade campos de progreso en instalaciones SQLite ya existentes."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(videos)"))}
        if "progress_stage" not in columns:
            connection.execute(text("ALTER TABLE videos ADD COLUMN progress_stage VARCHAR(40) DEFAULT 'completed'"))
        if "progress_percent" not in columns:
            connection.execute(text("ALTER TABLE videos ADD COLUMN progress_percent INTEGER DEFAULT 100"))
