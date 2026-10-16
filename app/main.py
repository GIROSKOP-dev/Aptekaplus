"""АптекаПлюс — FastAPI. Данные из PostgreSQL через asyncpg."""
import logging
import traceback
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, File, UploadFile
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


# ------------------------------------------------------------------
# Загрузка CSV: [DRUGS] + [BATCHES]
# ------------------------------------------------------------------
def _parse_sections(text: str):
    """Разбирает текст с секциями [DRUGS] и [BATCHES]."""
    import csv as _csv, io as _io

    drugs_rows, batches_rows, errors = [], [], []
    section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[DRUGS]":
            section = "drugs"; continue
        if line == "[BATCHES]":
            section = "batches"; continue
        if line.startswith("["):
            section = None; continue

        try:
            cells = next(_csv.reader(_io.StringIO(line)))
        except StopIteration:
            continue
        cells = [c.strip().strip('"') for c in cells]

        if section == "drugs":
            if cells[0].lower() == "id": continue
            if len(cells) < 8:
                errors.append(f"drugs: мало колонок — {line!r}")
                continue
            try:
                drugs_rows.append({
                    "csv_id": cells[0],
                    "name": cells[1], "form": cells[2],
                    "category": cells[3] or "Прочее",
                    "pack_size": int(cells[4]), "price_in": float(cells[5]),
                    "lead_time_days": int(cells[6]), "shelf_life_months": int(cells[7]),
                })
            except (ValueError, IndexError) as e:
                errors.append(f"drugs: {line!r} — {e}")

        elif section == "batches":
            if cells[0].lower() == "drugid": continue
            if len(cells) < 4:
                errors.append(f"batches: мало колонок — {line!r}")
                continue
            try:
                batches_rows.append({
                    "csv_drug_id": cells[0], "code": cells[1],
                    "qty": int(cells[2]),
                    "expiry": cells[3],
                    "box_opened":        len(cells) > 4 and cells[4] in ("1", "true", "True"),
                    "storage_violation": len(cells) > 5 and cells[5] in ("1", "true", "True"),
                    "recalled":          len(cells) > 6 and cells[6] in ("1", "true", "True"),
                })
            except (ValueError, IndexError) as e:
                errors.append(f"batches: {line!r} — {e}")

    return drugs_rows, batches_rows, errors


@app.post("/api/upload")
async def upload_data(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith((".csv", ".txt")):
        raise HTTPException(400, "Нужен CSV или TXT")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "Файл должен быть в UTF-8 (или UTF-8 with BOM)")

    drugs_rows, batches_rows, errors = _parse_sections(text)

    if not drugs_rows:
        raise HTTPException(400, {
            "message": "Не найдено ни одной строки в секции [DRUGS]",
            "errors": errors,
        })

    try:
        inserted = await db_api.bulk_append_from_csv(drugs_rows, batches_rows)
    except Exception as e:
        raise HTTPException(400, f"Ошибка записи в БД: {e}")

    return {
        "inserted": inserted,
        "errors": errors,
    }