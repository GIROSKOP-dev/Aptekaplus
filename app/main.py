"""PharmaStock — FastAPI-приложение. Данные — из PostgreSQL через asyncpg."""
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db_api
from app.config import DATABASE_URL
from app.services import loader

ALLOWED_MSL = (30, 45, 60, 90, 120)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_api.init_pool(DATABASE_URL)
    yield
    await db_api.close_pool()


app = FastAPI(title="PharmaStock", lifespan=lifespan)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    settings = await db_api.get_settings()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"allowed_msl": list(ALLOWED_MSL),
         "default_msl": settings["min_shelf_life_days"]},
    )


@app.get("/api/model")
async def api_model(msl: int = Query(60)):
    if msl not in ALLOWED_MSL:
        raise HTTPException(400, f"msl ∈ {list(ALLOWED_MSL)}")
    cfg, drugs = await loader.build_full_model(msl)
    return {
        "today": date.today().strftime("%d.%m.%Y"),
        "config": cfg,
        "drugs": drugs,
    }