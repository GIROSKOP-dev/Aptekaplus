"""Мост между БД и аналитикой.

Собирает данные из db_api, нормализует ключи (snake_case → camelCase),
передаёт в analytics.build_model.
"""
from app import db_api
from app.services import analytics


def _normalize_drug(row: dict) -> dict:
    """db_api-строка препарата → форма, которую ждёт analytics."""
    return {
        "id":       row["id"],
        "name":     row["name"],
        "form":     row["form"],
        "priceIn":  row["price_in"],
        "leadTime": row["lead_time_days"],
        "packSize": row["pack_size"],
        "minOrder": row["min_order_qty"],
    }


def _cfg_from_settings(settings: dict, msl: int) -> dict:
    return {
        "minShelfLifeDays": msl,
        "lossHorizonDays":  settings["loss_horizon_days"],
        "planningDays":     settings["planning_days"],
        "safetyFactor":     settings["safety_factor"],
        "historyDays":      settings["history_days"],
    }


async def build_full_model(msl: int):
    """Загрузить всё из БД и собрать модель. Возвращает (cfg, drugs)."""
    settings = await db_api.get_settings()
    drugs_raw = await db_api.get_drugs()
    batches_raw = await db_api.get_batches()
    sales_raw = await db_api.get_all_sales(settings["history_days"])

    # препараты — в форму analytics
    drugs = [_normalize_drug(r) for r in drugs_raw]

    # партии — группируем по drug_id
    batches_by_drug: dict[int, list[dict]] = {}
    for b in batches_raw:
        batches_by_drug.setdefault(b["drug_id"], []).append(b)

    cfg = _cfg_from_settings(settings, msl)
    model = analytics.build_model(drugs, batches_by_drug, sales_raw, cfg, msl)
    return cfg, model