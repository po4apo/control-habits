"""Приложение FastAPI и точка входа для uvicorn."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from starlette.staticfiles import StaticFiles

from control_habits.api.routes import activities, auth_link, report, schedule, users
from control_habits.config import Settings

# Корень проекта для раздачи static (src/control_habits/api/app.py -> 3 уровня вверх)
STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создание движка и фабрики сессий при старте."""
    settings = Settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )
    app.state.session_factory = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    yield
    engine.dispose()


app = FastAPI(
    title="Control Habits API",
    description="API привязки аккаунта и настройки расписания",
    lifespan=lifespan,
)


@app.exception_handler(OperationalError)
def _handle_db_unavailable(_request: Request, exc: OperationalError) -> JSONResponse:
    """При недоступности PostgreSQL возвращаем 503 с понятным текстом."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": "База данных недоступна. Запустите PostgreSQL и проверьте DATABASE_URL.",
            "hint": "Например: sudo systemctl start postgresql; alembic upgrade head",
        },
    )


app.include_router(auth_link.router, prefix="/api")
app.include_router(schedule.router, prefix="/api")
app.include_router(activities.router, prefix="/api")
app.include_router(report.router, prefix="/api")
app.include_router(users.router, prefix="/api")

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def _serve_index():
        """Главная страница — SPA."""
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}")
    def _serve_spa(full_path: str):
        """Все остальные не-API пути — index.html для SPA-роутинга."""
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(STATIC_DIR / "index.html")