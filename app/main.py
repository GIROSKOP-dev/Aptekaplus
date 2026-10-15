"""АптекаПлюс — FastAPI. Данные из PostgreSQL через asyncpg."""
import logging
import traceback
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db_api
from app.config import DATABASE_URL
from app.services import loader

logger = logging.getLogger("АптекаПлюс")
ALLOWED_PERIODS = (30, 90, 180, 365, 730, 1095)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db_api.init_pool(DATABASE_URL)
    yield
    await db_api.close_pool()


app = FastAPI(title="АптекаПлюс", lifespan=lifespan)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception):
    logger.error("Unhandled: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/model")
async def api_model(
    days: int = Query(365),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    if days not in ALLOWED_PERIODS:
        raise HTTPException(400, f"days ∈ {list(ALLOWED_PERIODS)}")
    if (date_from is None) ^ (date_to is None):
        raise HTTPException(400, "Укажи и date_from, и date_to")

    cfg, drugs, today = await loader.build_full_model(days, date_from, date_to)
    return {
        "today": today.strftime("%d.%m.%Y"),
        "config": cfg,
        "drugs": drugs,
    }