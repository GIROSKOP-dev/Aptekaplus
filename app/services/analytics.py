"""Чистая аналитика PharmaStock. Никакого I/O, никакого async.

Вход — уже нормализованные данные (camelCase-ключи, как ждёт фронт).
Выход — модель для отображения.

Все функции синхронные. Тестируются без БД.
"""
import math
from datetime import date, timedelta


def forecast_daily(sales: list[int]) -> float:
    """Линейная регрессия по последним 60 точкам + сглаживание со средним за 14 дней."""
    if not sales:
        return 0.5
    y = sales[-60:]
    n = len(y)
    if n < 2:
        return max(0.5, sum(y) / max(1, n))
    sx = n * (n - 1) / 2
    sy = sum(y)
    sxy = sum(i * v for i, v in enumerate(y))
    sxx = sum(i * i for i in range(n))
    den = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / den if den else 0
    intercept = (sy - slope * sx) / n
    reg = sum(max(0, intercept + slope * k) for k in range(n, n + 30)) / 30
    tail = y[-14:]
    return max(0.5, 0.75 * reg + 0.25 * sum(tail) / len(tail))


def simulate(batches, rate, horizon):
    """FEFO-симуляция. batches: [{"lastDay": int, "qty": int}, ...]."""
    items = [[b["lastDay"], b["qty"]] for b in batches]
    sold = lost = short = 0.0
    for day in range(horizon):
        for it in items:                 # списание того, у чего истёк срок продажи
            if it[1] > 0 and it[0] < day:
                lost += it[1]
                it[1] = 0
        need = rate
        for it in sorted(items, key=lambda x: x[0]):   # FEFO
            if need <= 0:
                break
            take = min(it[1], need)
            it[1] -= take
            sold += take
            need -= take
        if need > 0:
            short += need
    return sold, lost, short


def build_reasons(it, cfg):
    r = []
    if it["lossQty"] > 0:
        share = it["lossQty"] / max(1, it["stockTotal"]) * 100
        r.append(f"Из {it['stockTotal']:.0f} шт. {it['lossQty']:.0f} шт. "
                 f"({share:.0f}%) не удастся продать за {cfg['lossHorizonDays']} дн. "
                 f"Потери по закупке — {it['lossMoney']:,.0f} ₽.".replace(",", " "))
    if it["stockBlocked"] > 0:
        r.append(f"{it['stockBlocked']:.0f} шт. уже нельзя продавать: "
                 f"остаточный срок < {cfg['minShelfLifeDays']} дн.")
    prio = [b for b in it["batches"] if b.get("priority")]
    if prio:
        line = "; ".join(f"{b['code']} — {b['qty']} шт. до {b['lastSellable']}"
                         for b in prio[:3])
        r.append(f"FEFO-приоритет: {line}.")
    if it["overstock"]:
        r.append(f"Заказ не нужен: запаса хватит на {it['daysOfSupply']:.0f} дн.")
    elif it["orderQty"] > 0:
        r.append(f"Прогноз {it['forecast']:.1f} шт./дн × {it['horizon']} дн × "
                 f"{cfg['safetyFactor']} = {it['demand']:.0f} шт.; "
                 f"доступно {it['usable']:.0f} → дефицит {it['gap']:.0f} шт.")
        r.append(f"Округление до упаковки {it['packSize']} шт. "
                 f"(мин. {it['minOrder']}) → заказ {it['orderQty']} шт. "
                 f"на {it['orderValue']:,.0f} ₽, поставка {it['leadTime']} дн.".replace(",", " "))
    else:
        r.append(f"Заказ не нужен: запаса хватает на {it['horizon']} дн.")
    return r


def status_of(it):
    share = it["lossQty"] / max(1, it["stockTotal"])
    if it["lossQty"] > 0 and share >= 0.30 and it["overstock"]:
        return {"text": "Избыток + списание", "cls": "b-danger"}
    if it["shortage"] > 0 and it["daysOfSupply"] < it["leadTime"] + 10:
        return {"text": "Дефицит", "cls": "b-danger"}
    if it["lossQty"] > 0 and share >= 0.05:
        return {"text": "Риск списания", "cls": "b-warn"}
    if it["daysOfSupply"] > 120:
        return {"text": "Избыток", "cls": "b-warn"}
    if it["shortage"] > 0:
        return {"text": "Дефицит", "cls": "b-danger"}
    return {"text": "Норма", "cls": "b-ok"}


def build_model(drugs, batches_by_drug, sales_by_drug, cfg, msl, today=None):
    """Собирает полную модель для фронта.

    drugs            — [{id, name, form, priceIn, leadTime, packSize, minOrder}, ...]
    batches_by_drug  — {drug_id: [{code, qty_left, days_to_expiry}, ...]}
    sales_by_drug    — {drug_id: [qty, qty, ...]} по возрастанию даты
    cfg              — {lossHorizonDays, planningDays, safetyFactor, ...}
    msl              — минимальный остаточный срок годности
    """
    today = today or date.today()
    out = []

    for d in drugs:
        drug_id = d["id"]
        sales = sales_by_drug.get(drug_id, [])
        fc = forecast_daily(sales)

        raw_batches = batches_by_drug.get(drug_id, [])
        batches = sorted(
            ({"code": b["code"], "qty": b["qty_left"],
              "lastDay": b["days_to_expiry"] - msl}
             for b in raw_batches),
            key=lambda b: b["lastDay"],
        )

        n = 0
        for b in batches:
            b["blocked"] = b["lastDay"] < 0
            b["lastSellable"] = (
                today + timedelta(days=max(0, b["lastDay"]))
            ).strftime("%d.%m.%Y")
            if not b["blocked"] and b["qty"] > 0:
                n += 1
                b["priority"] = n
            else:
                b["priority"] = None

        total = sum(b["qty"] for b in batches)
        sellable = sum(b["qty"] for b in batches if b["lastDay"] >= 0)

        _, lost, _ = simulate(batches, fc, cfg["lossHorizonDays"])
        horizon = d["leadTime"] + cfg["planningDays"]
        usable, _, short_plan = simulate(batches, fc, horizon)

        demand = fc * horizon * cfg["safetyFactor"]
        gap = max(0.0, demand - usable)
        overstock = total > demand * 1.5
        shortage = max(0.0, short_plan - (demand - fc * horizon))

        order = 0
        if not overstock and gap > 0:
            order = max(math.ceil(gap / d["packSize"]) * d["packSize"], d["minOrder"])

        item = dict(
            id=d["id"], name=d["name"], form=d["form"],
            priceIn=d["priceIn"], leadTime=d["leadTime"],
            packSize=d["packSize"], minOrder=d["minOrder"],
            batches=batches, sales=sales, forecast=fc,
            stockTotal=total, stockSellable=sellable,
            stockBlocked=total - sellable,
            stockBlockedMoney=(total - sellable) * d["priceIn"],
            lossQty=lost, lossMoney=lost * d["priceIn"],
            shortage=shortage,
            daysOfSupply=(sellable / fc) if fc > 0 else 9999,
            horizon=horizon, demand=demand, usable=usable, gap=gap,
            overstock=overstock, orderQty=order, orderValue=order * d["priceIn"],
        )
        item["status"] = status_of(item)
        item["reasons"] = build_reasons(item, cfg)
        out.append(item)

    return out