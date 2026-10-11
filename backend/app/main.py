"""Aplicación FastAPI del backend del prototipo."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes import router
from app.api.routes_auth import router as auth_router
from app.api.routes_groups import router as groups_router
from app.core.config import get_settings
from app.core.errors import PipelineError
from app.db.database import Base, engine
from app.models.group import Attempt, Group, GroupMembership, Topic  # noqa: F401 - registra modelos antes de create_all
from app.models.material import DidacticMaterial, MaterialVersion  # noqa: F401
from app.models.user import User  # noqa: F401 - registra el modelo antes de create_all
from app.models.video import Video  # noqa: F401 - registra el modelo antes de create_all

app = FastAPI(title="YouTube Didactic Material API", version="0.1.0")
app.include_router(router)
app.include_router(auth_router)
app.include_router(groups_router)
WEB_DIRECTORY = Path(__file__).resolve().parent / "web"
app.mount("/ui", StaticFiles(directory=WEB_DIRECTORY, html=True), name="ui")


@app.get("/", include_in_schema=False)
def open_visual_interface() -> RedirectResponse:
    """Redirige a la interfaz visual; el frontend decide si ir a auth o a videos."""
    return RedirectResponse(url="/ui/auth/")


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
    get_settings().ensure_data_directories()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(videos)"))}
        if "progress_stage" not in columns:
            connection.execute(text("ALTER TABLE videos ADD COLUMN progress_stage VARCHAR(40) DEFAULT 'completed'"))
        if "progress_percent" not in columns:
            connection.execute(text("ALTER TABLE videos ADD COLUMN progress_percent INTEGER DEFAULT 100"))
        if "owner_id" not in columns:
            connection.execute(text("ALTER TABLE videos ADD COLUMN owner_id INTEGER DEFAULT NULL"))
        if "created_at" not in columns:
            connection.execute(text("ALTER TABLE videos ADD COLUMN created_at DATETIME DEFAULT NULL"))
        topic_cols = {row[1] for row in connection.execute(text("PRAGMA table_info(topics)"))}
        if "video_id" not in topic_cols:
            connection.execute(text("ALTER TABLE topics ADD COLUMN video_id INTEGER DEFAULT NULL"))
        mat_cols = {row[1] for row in connection.execute(text("PRAGMA table_info(didactic_materials)"))}
        if "owner_id" not in mat_cols:
            connection.execute(text("ALTER TABLE didactic_materials ADD COLUMN owner_id INTEGER DEFAULT NULL"))
        group_cols = {row[1] for row in connection.execute(text("PRAGMA table_info(groups)"))}
        if "code" not in group_cols:
            connection.execute(text("ALTER TABLE groups ADD COLUMN code VARCHAR(6) DEFAULT NULL"))
            # Asignar un código alfanumérico único a cada grupo existente
            import secrets, string
            rows = connection.execute(text("SELECT id FROM groups WHERE code IS NULL")).fetchall()
            for r in rows:
                generated_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
                connection.execute(text(f"UPDATE groups SET code = '{generated_code}' WHERE id = {r[0]}"))

        if "material_id" not in topic_cols:
            connection.execute(text("ALTER TABLE topics ADD COLUMN material_id INTEGER DEFAULT NULL"))
        if "created_by" not in topic_cols:
            connection.execute(text("ALTER TABLE topics ADD COLUMN created_by INTEGER DEFAULT NULL"))
        if "is_active" not in topic_cols:
            connection.execute(text("ALTER TABLE topics ADD COLUMN is_active BOOLEAN DEFAULT 1"))

        # Migrar membresías existentes de group_members a group_memberships si aplica
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        if "group_members" in tables and "group_memberships" in tables:
            connection.execute(text("""
                INSERT OR IGNORE INTO group_memberships (group_id, user_id, joined_at)
                SELECT group_id, user_id, joined_at FROM group_members
            """))

