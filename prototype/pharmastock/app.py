"""PharmaStock — управление запасами лекарств (FastAPI, компактная версия)."""
import math
import random
from datetime import date, timedelta

import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="PharmaStock")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

CFG = dict(minShelfLifeDays=60, lossHorizonDays=180, planningDays=30,
           safetyFactor=1.15, historyDays=120)
ALLOWED_MSL = (30, 45, 60, 90, 120)

DRUGS_RAW = [
    dict(id="amox", name="Амоксициллин", form="капс. 500 мг №20",
         priceIn=78, leadTime=14, packSize=100, minOrder=100,
         baseSales=40, salesStart=0.80, salesEnd=1.20, weekendFactor=0.85, seed=101,
         batches=[dict(code="AM-2417", qty=260, expires=72),
                  dict(code="AM-2431", qty=480, expires=265),
                  dict(code="AM-2444", qty=300, expires=480)]),
    dict(id="para", name="Парацетамол", form="табл. 500 мг №20",
         priceIn=22, leadTime=10, packSize=200, minOrder=200,
         baseSales=62, salesStart=1.00, salesEnd=1.05, weekendFactor=0.95, seed=202,
         batches=[dict(code="PR-1180", qty=420, expires=175),
                  dict(code="PR-1205", qty=900, expires=400),
                  dict(code="PR-1233", qty=650, expires=610)]),
    # DEMO: обязательный кейс ТЗ — много запаса, значительная часть скоро неликвидна.
    dict(id="asc", name="Аскорбиновая кислота", form="драже 500 мг №50",
         priceIn=35, leadTime=21, packSize=500, minOrder=500, demo=True,
         baseSales=18, salesStart=1.90, salesEnd=0.35, weekendFactor=0.90, seed=303,
         batches=[dict(code="AS-0912", qty=3000, expires=65),
                  dict(code="AS-1004", qty=1500, expires=150),
                  dict(code="AS-1050", qty=1200, expires=400)]),
    dict(id="ome", name="Омепразол", form="капс. 20 мг №30",
         priceIn=55, leadTime=12, packSize=150, minOrder=150,
         baseSales=28, salesStart=0.95, salesEnd=1.10, weekendFactor=0.95, seed=404,
         batches=[dict(code="OM-3301", qty=210, expires=96),
                  dict(code="OM-3320", qty=620, expires=300),
                  dict(code="OM-3344", qty=340, expires=500)]),
    dict(id="lor", name="Лоратадин", form="табл. 10 мг №10",
         priceIn=18, leadTime=7, packSize=200, minOrder=200,
         baseSales=20, salesStart=1.60, salesEnd=0.55, weekendFactor=0.90, seed=505,
         batches=[dict(code="LO-2207", qty=400, expires=78),
                  dict(code="LO-2240", qty=1400, expires=380),
                  dict(code="LO-2288", qty=900, expires=560)]),
    dict(id="azi", name="Азитромицин", form="табл. 500 мг №3",
         priceIn=120, leadTime=20, packSize=50, minOrder=50,
         baseSales=11, salesStart=1.00, salesEnd=1.00, weekendFactor=0.90, seed=606,
         batches=[dict(code="AZ-5510", qty=90, expires=210),
                  dict(code="AZ-5528", qty=45, expires=430)]),
    dict(id="met", name="Метформин", form="табл. 1000 мг №60",
         priceIn=95, leadTime=14, packSize=100, minOrder=100,
         baseSales=17, salesStart=1.00, salesEnd=1.08, weekendFactor=0.95, seed=707,
         batches=[dict(code="ME-8801", qty=320, expires=155),
                  dict(code="ME-8820", qty=520, expires=430)]),
    dict(id="ibu", name="Ибупрофен", form="табл. 400 мг №20",
         priceIn=30, leadTime=9, packSize=200, minOrder=200,
         baseSales=33, salesStart=0.90, salesEnd=1.12, weekendFactor=0.90, seed=808,
         batches=[dict(code="IB-4415", qty=140, expires=71),
                  dict(code="IB-4430", qty=720, expires=250),
                  dict(code="IB-4451", qty=410, expires=470)]),
    dict(id="cet", name="Цетиризин", form="табл. 10 мг №20",
         priceIn=25, leadTime=8, packSize=100, minOrder=100,
         baseSales=16, salesStart=1.50, salesEnd=0.60, weekendFactor=0.90, seed=909,
         batches=[dict(code="CE-7702", qty=900, expires=100),
                  dict(code="CE-7740", qty=1100, expires=410)]),
    dict(id="dro", name="Дротаверин", form="табл. 40 мг №20",
         priceIn=42, leadTime=15, packSize=100, minOrder=100,
         baseSales=19, salesStart=1.00, salesEnd=1.02, weekendFactor=0.95, seed=1010,
         batches=[dict(code="DR-6604", qty=380, expires=310),
                  dict(code="DR-6621", qty=240, expires=530)]),
]


# ---------- Прогноз ----------
def gen_sales(d, today):
    rnd = random.Random(d["seed"])
    n = CFG["historyDays"]
    out = []
    for i in range(n - 1, -1, -1):
        t = (n - 1 - i) / (n - 1)
        trend = d["salesStart"] + (d["salesEnd"] - d["salesStart"]) * t
        weekly = d["weekendFactor"] if (today - timedelta(days=i)).weekday() >= 5 else 1
        out.append(max(0, round(d["baseSales"] * trend * weekly * (0.85 + 0.30 * rnd.random()))))
    return out


def forecast_daily(sales):
    y = sales[-60:]
    n = len(y)
    sx = n * (n - 1) / 2
    sy = sum(y)
    sxy = sum(i * v for i, v in enumerate(y))
    sxx = sum(i * i for i in range(n))
    den = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / den if den else 0
    intercept = (sy - slope * sx) / n
    reg = sum(max(0, intercept + slope * k) for k in range(n, n + 30)) / 30
    return max(0.5, 0.75 * reg + 0.25 * sum(y[-14:]) / 14)


# ---------- FEFO-симуляция ----------
def simulate(batches, rate, horizon):
    """[lastDay, left] на каждую партию. Продаём по возрастанию lastDay."""
    items = [[b["lastDay"], b["qty"]] for b in batches]
    sold = lost = short = 0.0
    for day in range(horizon):
        for it in items:  # списание того, у чего истёк срок продажи
            if it[1] > 0 and it[0] < day:
                lost += it[1]
                it[1] = 0
        need = rate
        for it in sorted(items, key=lambda x: x[0]):  # FEFO
            if need <= 0:
                break
            take = min(it[1], need)
            it[1] -= take
            sold += take
            need -= take
        if need > 0:
            short += need
    return sold, lost, short


# ---------- Причины и статусы ----------
def build_reasons(it, msl):
    r = []
    if it["lossQty"] > 0:
        share = it["lossQty"] / it["stockTotal"] * 100
        r.append(f"Из {it['stockTotal']:.0f} шт. {it['lossQty']:.0f} шт. "
                 f"({share:.0f}%) не удастся продать за {CFG['lossHorizonDays']} дн. "
                 f"Потери по закупке — {it['lossMoney']:,.0f} ₽.".replace(",", " "))
    if it["stockBlocked"] > 0:
        r.append(f"{it['stockBlocked']:.0f} шт. уже нельзя продавать: "
                 f"остаточный срок < {msl} дн.")
    prio = [b for b in it["batches"] if b["priority"]]
    if prio:
        line = "; ".join(f"{b['code']} — {b['qty']} шт. до {b['lastSellable']}"
                         for b in prio[:3])
        r.append(f"FEFO-приоритет: {line}.")
    if it["overstock"]:
        r.append(f"Заказ не нужен: запаса хватит на {it['daysOfSupply']:.0f} дн.")
    elif it["orderQty"] > 0:
        r.append(f"Прогноз {it['forecast']:.1f} шт./дн × {it['horizon']} дн × "
                 f"{CFG['safetyFactor']} = {it['demand']:.0f} шт.; "
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


# ---------- Модель ----------
def build_model(msl, today=None):
    today = today or date.today()
    out = []
    for d in DRUGS_RAW:
        sales = gen_sales(d, today)
        fc = forecast_daily(sales)

        batches = sorted(
            (dict(code=b["code"], qty=b["qty"], lastDay=b["expires"] - msl)
             for b in d["batches"]),
            key=lambda b: b["lastDay"])
        n = 0
        for b in batches:
            b["blocked"] = b["lastDay"] < 0
            b["lastSellable"] = (today + timedelta(days=max(0, b["lastDay"]))).strftime("%d.%m.%Y")
            if not b["blocked"] and b["qty"] > 0:
                n += 1
                b["priority"] = n
            else:
                b["priority"] = None

        total = sum(b["qty"] for b in batches)
        sellable = sum(b["qty"] for b in batches if b["lastDay"] >= 0)

        _, lost, _ = simulate(batches, fc, CFG["lossHorizonDays"])
        horizon = d["leadTime"] + CFG["planningDays"]
        usable, _, short_plan = simulate(batches, fc, horizon)

        demand = fc * horizon * CFG["safetyFactor"]
        gap = max(0.0, demand - usable)
        overstock = total > demand * 1.5
        shortage = max(0.0, short_plan - (demand - fc * horizon))

        order = 0
        if not overstock and gap > 0:
            order = max(math.ceil(gap / d["packSize"]) * d["packSize"], d["minOrder"])

        item = dict(
            id=d["id"], name=d["name"], form=d["form"], demo=d.get("demo", False),
            priceIn=d["priceIn"], leadTime=d["leadTime"],
            packSize=d["packSize"], minOrder=d["minOrder"],
            batches=batches, sales=sales, forecast=fc,
            stockTotal=total, stockSellable=sellable,
            stockBlocked=total - sellable,
            stockBlockedMoney=(total - sellable) * d["priceIn"],
            lossQty=lost, lossMoney=lost * d["priceIn"],
            shortage=shortage, daysOfSupply=sellable / fc,
            horizon=horizon, demand=demand, usable=usable, gap=gap,
            overstock=overstock, orderQty=order, orderValue=order * d["priceIn"],
        )
        item["status"] = status_of(item)
        item["reasons"] = build_reasons(item, msl)
        out.append(item)
    return out


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,                    # ← request теперь ПЕРВЫЙ аргумент
        "index.html",
        {"allowed_msl": list(ALLOWED_MSL),
         "default_msl": CFG["minShelfLifeDays"]},
    )

@app.get("/api/model")
def api_model(msl: int = Query(60)):
    if msl not in ALLOWED_MSL:
        raise HTTPException(400, f"msl ∈ {list(ALLOWED_MSL)}")
    return {"today": date.today().strftime("%d.%m.%Y"),
            "config": {**CFG, "minShelfLifeDays": msl},
            "drugs": build_model(msl)}


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8080, reload=True)