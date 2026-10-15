"""Чистая аналитика АптекаПлюс: правило 60%, сезонность, статусы партий."""
from __future__ import annotations
import math
from datetime import date, timedelta
from typing import Optional

SEASON_MONTHS = {"winter": (12,1,2), "spring": (3,4,5), "summer": (6,7,8), "autumn": (9,10,11)}
SEASON_NAMES   = {"winter":"Зима","spring":"Весна","summer":"Лето","autumn":"Осень"}
SEASON_NAMES_IN= {"winter":"зимой","spring":"весной","summer":"летом","autumn":"осенью"}

BLOCK_LABELS = {
    "expired": {"label":"❌ Просрочен","cls":"b-danger","hint":"Срок истёк — только утилизация."},
    "recall":  {"label":"🚫 Отзыв","cls":"b-danger","hint":"Отзыв производителя — вернуть поставщику."},
    "storage": {"label":"🌡️ Хранение","cls":"b-warn","hint":"Нарушены условия хранения — списание."},
    "box":     {"label":"📦 Коробка","cls":"b-warn","hint":"Вскрыта транспортная коробка — списание."},
    "expiry":  {"label":"⏳ Срок ≤60%","cls":"b-danger","hint":"Остаточный срок ≤60% — брак. Утилизация или возврат."},
}


# ---------- утилиты ----------
def _mean(a): return sum(a) / len(a) if a else 0.0

def _linear_trend(values):
    n = len(values)
    if n < 2: return 0.0
    mx = (n - 1) / 2
    my = _mean(values)
    num = den = 0.0
    for i, v in enumerate(values):
        num += (i - mx) * (v - my)
        den += (i - mx) ** 2
    return num / den if den else 0.0


def current_season(d: date) -> str:
    for s, ms in SEASON_MONTHS.items():
        if d.month in ms: return s
    return "autumn"


# ---------- период анализа ----------
def get_analysis_slice(sales, cfg, today):
    n = len(sales)
    f, t = cfg.get("analysisFrom"), cfg.get("analysisTo")
    if f and t:
        start = max(0, n - (today - f).days - 1)
        end   = max(0, n - (today - t).days)
        return sales[start:end] if end > start else sales[-30:]
    days = cfg.get("analysisDays", 365)
    return sales if days >= n else sales[-days:]


def forecast_demand(sales, cfg, today):
    sl = get_analysis_slice(sales, cfg, today)
    recent = sl[-60:]
    avg14 = _mean(sl[-14:]) if sl else 0
    trend = _linear_trend(recent)
    last = recent[-1] if recent else 0
    base = max(0.1, last + trend * 30)
    return max(0.1, base * 0.75 + avg14 * 0.25)


# ---------- сезон ----------
def peak_season(profile):
    if not profile: return {"season": "winter", "mult": 1.0}
    if isinstance(profile, str):
        import json
        profile = json.loads(profile)   # подстраховка на «старые» строки
    best = max(profile.items(), key=lambda kv: kv[1])
    return {"season": best[0], "mult": float(best[1])}


def is_seasonal(profile, threshold):
    return profile is not None and peak_season(profile)["mult"] >= threshold


def avg_by_season(sales, profile, season, cfg, today):
    if not profile: return _mean(sales)
    sl = get_analysis_slice(sales, cfg, today)
    month_set = set(SEASON_MONTHS[season])
    vals = []
    for i, v in enumerate(sl):
        d = today - timedelta(days=len(sl) - 1 - i)
        if d.month in month_set: vals.append(v)
    return _mean(vals) if vals else _mean(sl)


# ---------- правило 60% ----------
def total_shelf_life_days(drug): return drug["shelf_life_months"] * 30
def days_until_expiry(b, today): return (b["expires_at"] - today).days
def days_until_block(b, drug, today, block_percent):
    return round(days_until_expiry(b, today) - total_shelf_life_days(drug) * block_percent)
def percent_left(b, drug, today):
    return days_until_expiry(b, today) / total_shelf_life_days(drug) * 100


def get_block_reason(b, drug, today, block_percent):
    if b.get("recalled"):          return "recall"
    if b.get("storage_violation"): return "storage"
    if b.get("box_opened"):        return "box"
    if days_until_expiry(b, today) <= 0: return "expired"
    if percent_left(b, drug, today) <= block_percent * 100: return "expiry"
    return None


# ---------- статус партии ----------
def get_batch_status(b, drug, avg_daily, cfg, today):
    bp  = cfg["blockPercent"]
    reason = get_block_reason(b, drug, today, bp)
    dtb    = days_until_block(b, drug, today, bp)
    if reason:
        return {"key": f"blocked-{reason}", "label": BLOCK_LABELS[reason]["label"],
                "cls": BLOCK_LABELS[reason]["cls"], "priority": "high",
                "hint": BLOCK_LABELS[reason]["hint"], "coverage": 0,
                "daysToBlock": dtb, "ratio": 0}

    coverage = round(b["qty"] / avg_daily) if avg_daily > 0.1 else 9999
    ratio = coverage / dtb if dtb > 0 else 999

    if   ratio <= 0.7:                  key,label,cls,prio = "ok",  "В НОРМЕ","b-ok","low"
    elif ratio <= cfg["tightRatio"]:    key,label,cls,prio = "soon","СКОРО","b-warn","medium"
    elif ratio <= 1.0:                  key,label,cls,prio = "warn","ВНИМАНИЕ","b-warn","medium"
    elif ratio <= cfg["warnRatio"]:     key,label,cls,prio = "warn","ВНИМАНИЕ","b-warn","medium"
    else:                               key,label,cls,prio = "critical","КРИТИЧНО","b-danger","high"

    return {"key": key, "label": label, "cls": cls, "priority": prio,
            "hint": f"Покрытие {coverage} дн., до порога 60% — {dtb} дн.",
            "coverage": coverage, "daysToBlock": dtb, "ratio": round(ratio, 3)}


# ---------- заказ ----------
def calc_order(drug, forecast, usable, overstock, cfg):
    horizon = drug["lead_time_days"] + cfg["planningDays"]
    demand  = forecast * horizon * cfg["safetyFactor"]
    deficit = max(0.0, demand - usable)
    if overstock or deficit <= 0:
        return {"qty": 0, "demand": demand, "deficit": deficit, "orderValue": 0.0}
    qty = math.ceil(deficit / drug["pack_size"]) * drug["pack_size"]
    return {"qty": qty, "demand": demand, "deficit": deficit,
            "orderValue": qty * drug["price_in"]}


def calc_seasonal_order(drug, peak_avg, usable, cfg):
    horizon = drug["lead_time_days"] + cfg["planningDays"]
    peak_demand = peak_avg * horizon * cfg["safetyFactor"]
    deficit = max(0.0, peak_demand - usable)
    if deficit <= 0:
        return {"qty": 0, "peakDemand": peak_demand, "deficit": 0, "orderValue": 0.0}
    qty = math.ceil(deficit / drug["pack_size"]) * drug["pack_size"]
    return {"qty": qty, "peakDemand": peak_demand, "deficit": deficit,
            "orderValue": qty * drug["price_in"]}


# ---------- срочность заказа ----------
def order_urgency(days_to_block: int, lead_time: int) -> dict:
    """Сравниваем дни до порога 60% со сроком поставки."""
    dtb = max(0, int(days_to_block))
    if dtb <= lead_time:
        return {"level": "urgent", "label": "🔴 СРОЧНО", "cls": "b-urgent",
                "rank": 0, "minDTB": dtb}
    if dtb <= lead_time * 2:
        return {"level": "soon", "label": "🟠 Успеть", "cls": "b-warn",
                "rank": 1, "minDTB": dtb}
    return {"level": "plan", "label": "🟢 Плановый", "cls": "b-ok",
            "rank": 2, "minDTB": dtb}


# ---------- анализ препарата ----------
def analyze_drug(drug, batches_raw, sales, cfg, today):
    fc = forecast_demand(sales, cfg, today)
    sl = get_analysis_slice(sales, cfg, today)
    avg14 = _mean(sl[-14:]) if sl else 0.0
    avg28 = _mean(sl[-28:]) if sl else 0.0
    avg_cov = avg14 if avg14 > 0 else fc
    stock_total = sum(b["qty"] for b in batches_raw)
    bp = cfg["blockPercent"]
    lt = drug["lead_time_days"]

    batches = []
    for b in batches_raw:
        reason = get_block_reason(b, drug, today, bp)
        status = get_batch_status(b, drug, avg_cov, cfg, today)
        coverage = status["coverage"]
        dtb = status["daysToBlock"]
        pct = percent_left(b, drug, today)

        if reason:
            sold, lost = 0, b["qty"]
        else:
            can = min(b["qty"], math.floor(avg_cov * max(0, dtb)))
            sold, lost = can, b["qty"] - can

        # срочность на уровне партии
        u_b = order_urgency(dtb, lt) if not reason else \
              {"level": "blocked", "label": "—", "cls": "b-ok",
               "rank": -1, "minDTB": 0}

        batches.append({
            **b,
            "expiryDate": b["expires_at"].strftime("%d.%m.%Y"),
            "expDateIso": b["expires_at"].isoformat(),
            "blockReason": reason,
            "blockLabel": BLOCK_LABELS[reason]["label"] if reason else None,
            "status": status,
            "sold": sold, "lost": lost,
            "coverage": coverage, "daysToBlock": dtb,
            "percentLeft": round(pct, 1),
            "lastDay": max(0, dtb),
            "urgency": u_b,
        })

    loss_qty = sum(b["lost"] for b in batches)
    loss_money = loss_qty * drug["price_in"]
    stock_sellable = sum(b["qty"] - b["lost"] for b in batches if not b["blockReason"])
    dos = stock_total / fc if fc > 0 else 999
    horizon = drug["lead_time_days"] + cfg["planningDays"]
    overstock = stock_total > fc * horizon * cfg["overstockThresh"]
    order = calc_order(drug, fc, stock_sellable, overstock, cfg)
    shortage = max(0.0, fc * drug["lead_time_days"] - stock_sellable)

    peak = peak_season(drug.get("season_profile"))
    peak_avg = avg_by_season(sales, drug.get("season_profile"), peak["season"], cfg, today)
    seasonal = is_seasonal(drug.get("season_profile"), cfg["seasonThreshold"])
    s_order = calc_seasonal_order(drug, peak_avg, stock_sellable, cfg) if seasonal else \
              {"qty": 0, "peakDemand": 0, "deficit": 0, "orderValue": 0}

    # срочность на уровне препарата (по самой «горящей» продаваемой партии)
    sellable_dtbs = [b["daysToBlock"] for b in batches if not b["blockReason"]]
    if not sellable_dtbs:
        urgency = {
            "level": "urgent", "label": "🔴 СРОЧНО",
            "cls": "b-urgent", "rank": 0, "minDTB": 0,
            "reason": "Нет продаваемых партий — нулевой остаток, заказ критичен.",
        }
    else:
        min_dtb = min(sellable_dtbs)
        urgency = order_urgency(min_dtb, lt)
        if urgency["level"] == "urgent":
            urgency["reason"] = f"До порога {min_dtb} дн. ≤ поставка {lt} дн. — не успеваем."
        elif urgency["level"] == "soon":
            urgency["reason"] = f"Поставка {lt} дн., порог через {min_dtb} дн. — успеть."
        else:
            urgency["reason"] = f"Поставка {lt} дн., порог через {min_dtb} дн."

            
    if any(b["blockReason"] in ("expired", "recall") for b in batches):
        status = {"cls": "b-danger", "text": "Брак/отзыв"}
    elif any(b["blockReason"] for b in batches):
        status = {"cls": "b-danger", "text": "Есть брак"}
    elif shortage > 1:
        status = {"cls": "b-danger", "text": "Дефицит"}
    elif loss_qty > 0.5:
        status = {"cls": "b-warn", "text": "Риск списания"}
    elif seasonal and s_order["qty"] > 0:
        status = {"cls": "b-warn", "text": "Сезонный заказ"}
    elif overstock:
        status = {"cls": "b-warn", "text": "Избыток"}
    else:
        status = {"cls": "b-ok", "text": "Норма"}

    return {
        "id": drug["id"], "name": drug["name"], "form": drug["form"],
        "category": drug["category"], "priceIn": drug["price_in"],
        "leadTime": drug["lead_time_days"], "packSize": drug["pack_size"],
        "shelfLifeMonths": drug["shelf_life_months"], "trend": drug["trend"],
        "seasonProfile": drug.get("season_profile"),
        "forecast": round(fc, 2), "avg14": round(avg14, 2), "avg28": round(avg28, 2),
        "stockTotal": stock_total, "stockSellable": stock_sellable,
        "batches": batches, "sales": list(map(int, sales)),
        "lossQty": loss_qty, "lossMoney": round(loss_money, 2),
        "daysOfSupply": round(dos, 1),
        "shortage": round(shortage, 2), "overstock": overstock,
        "horizon": horizon,
        "orderQty": order["qty"], "demand": round(order["demand"], 1),
        "orderValue": round(order["orderValue"], 2),
        "usable": stock_sellable, "status": status,
        "peakSeason": peak["season"], "peakMult": peak["mult"],
        "peakAvg": round(peak_avg, 2), "isSeasonal": seasonal,
        "seasonNow": current_season(today),
        "seasonNowAvg": round(avg_by_season(sales, drug.get("season_profile"),
                                            current_season(today), cfg, today), 2),
        "seasonalOrderQty": s_order["qty"],
        "seasonalOrderValue": round(s_order["orderValue"], 2),
        "urgency": urgency,
    }


def build_model(drugs, batches_by_drug, sales_by_drug, cfg, today):
    return [analyze_drug(d, batches_by_drug.get(d["id"], []),
                         sales_by_drug.get(d["id"], []), cfg, today)
            for d in drugs]