"""Мост между БД и аналитикой."""
from datetime import date
from typing import Any, Optional

from app import db_api
from app.services import analytics


async def build_full_model(
    analysis_days: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], date]:
    """Загрузить всё из БД, собрать модель. Возвращает (cfg, drugs, today)."""
    s = await db_api.get_settings()
    drugs = await db_api.get_drugs()
    batches = await db_api.get_batches()
    sales = await db_api.get_all_sales(s["history_days"])

    batches_by_drug: dict[int, list[dict[str, Any]]] = {}
    for b in batches:
        batches_by_drug.setdefault(b["drug_id"], []).append(b)

    cfg: dict[str, Any] = {
        "planningDays":     s["planning_days"],
        "safetyFactor":     s["safety_factor"],
        "historyDays":      s["history_days"],
        "blockPercent":     s["block_percent"],
        "seasonThreshold":  s["season_threshold"],
        "overstockThresh":  s["overstock_thresh"],
        "tightRatio":       s["tight_ratio"],
        "warnRatio":        s["warn_ratio"],
        "analysisDays":     analysis_days or s["analysis_days"],
        "analysisFrom":     date.fromisoformat(date_from) if date_from else None,
        "analysisTo":       date.fromisoformat(date_to)   if date_to   else None,
    }
    today = date.today()
    model = analytics.build_model(drugs, batches_by_drug, sales, cfg, today)
    return cfg, model, today