"""PharmaStock — управление запасами лекарств.

Бэкенд на Flask: вся аналитика (генерация истории продаж, прогноз спроса,
FEFO-симуляция списаний, рекомендации по закупке) считается на Python,
фронтенд получает готовую модель через /api/model.

Запуск:  python app.py   →  http://127.0.0.1:5000
"""
import math
from datetime import date, timedelta

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ------------------------------------------------------------------
# Конфигурация
# ------------------------------------------------------------------
CFG = {
    "minShelfLifeDays": 60,   # минимальный остаточный срок годности для продажи
    "lossHorizonDays": 180,   # горизонт прогноза списаний
    "planningDays": 30,       # период планирования после поставки
    "safetyFactor": 1.15,     # коэффициент страхового запаса
    "historyDays": 120,       # глубина истории продаж
}
ALLOWED_MSL = (30, 45, 60, 90, 120)

# ------------------------------------------------------------------
# Данные (вымышленные)
# ------------------------------------------------------------------
DRUGS_RAW = [
    dict(id="amox", name="Амоксициллин", form="капс. 500 мг №20",
         priceIn=78, priceOut=145, leadTime=14, packSize=100, minOrder=100,
         baseSales=40, salesStart=0.80, salesEnd=1.20, weekendFactor=0.85, seed=101,
         batches=[
             dict(code="AM-2417", qty=260, expires=72, arrived=45),
             dict(code="AM-2431", qty=480, expires=265, arrived=20),
             dict(code="AM-2444", qty=300, expires=480, arrived=4)]),
    dict(id="para", name="Парацетамол", form="табл. 500 мг №20",
         priceIn=22, priceOut=45, leadTime=10, packSize=200, minOrder=200,
         baseSales=62, salesStart=1.00, salesEnd=1.05, weekendFactor=0.95, seed=202,
         batches=[
             dict(code="PR-1180", qty=420, expires=175, arrived=60),
             dict(code="PR-1205", qty=900, expires=400, arrived=25),
             dict(code="PR-1233", qty=650, expires=610, arrived=6)]),
    dict(id="asc", name="Аскорбиновая кислота", form="драже 500 мг №50",
         priceIn=35, priceOut=79, leadTime=21, packSize=500, minOrder=500,
         baseSales=18, salesStart=1.90, salesEnd=0.35, weekendFactor=0.90, seed=303,
         batches=[
             dict(code="AS-0912", qty=3000, expires=65, arrived=120),
             dict(code="AS-1004", qty=1500, expires=150, arrived=70),
             dict(code="AS-1050", qty=1200, expires=400, arrived=15)]),
    dict(id="ome", name="Омепразол", form="капс. 20 мг №30",
         priceIn=55, priceOut=110, leadTime=12, packSize=150, minOrder=150,
         baseSales=28, salesStart=0.95, salesEnd=1.10, weekendFactor=0.95, seed=404,
         batches=[
             dict(code="OM-3301", qty=210, expires=96, arrived=50),
             dict(code="OM-3320", qty=620, expires=300, arrived=30),
             dict(code="OM-3344", qty=340, expires=500, arrived=8)]),
    dict(id="lor", name="Лоратадин", form="табл. 10 мг №10",
         priceIn=18, priceOut=42, leadTime=7, packSize=200, minOrder=200,
         baseSales=20, salesStart=1.60, salesEnd=0.55, weekendFactor=0.90, seed=505,
         batches=[
             dict(code="LO-2207", qty=400, expires=78, arrived=90),
             dict(code="LO-2240", qty=1400, expires=380, arrived=40),
             dict(code="LO-2288", qty=900, expires=560, arrived=10)]),
    dict(id="azi", name="Азитромицин", form="табл. 500 мг №3",
         priceIn=120, priceOut=235, leadTime=20, packSize=50, minOrder=50,
         baseSales=11, salesStart=1.00, salesEnd=1.00, weekendFactor=0.90, seed=606,
         batches=[
             dict(code="AZ-5510", qty=90, expires=210, arrived=55),
             dict(code="AZ-5528", qty=45, expires=430, arrived=12)]),
    dict(id="met", name="Метформин", form="табл. 1000 мг №60",
         priceIn=95, priceOut=185, leadTime=14, packSize=100, minOrder=100,
         baseSales=17, salesStart=1.00, salesEnd=1.08, weekendFactor=0.95, seed=707,
         batches=[
             dict(code="ME-8801", qty=320, expires=155, arrived=65),
             dict(code="ME-8820", qty=520, expires=430, arrived=22)]),
    dict(id="ibu", name="Ибупрофен", form="табл. 400 мг №20",
         priceIn=30, priceOut=68, leadTime=9, packSize=200, minOrder=200,
         baseSales=33, salesStart=0.90, salesEnd=1.12, weekendFactor=0.90, seed=808,
         batches=[
             dict(code="IB-4415", qty=140, expires=71, arrived=70),
             dict(code="IB-4430", qty=720, expires=250, arrived=35),
             dict(code="IB-4451", qty=410, expires=470, arrived=9)]),
    dict(id="cet", name="Цетиризин", form="табл. 10 мг №20",
         priceIn=25, priceOut=58, leadTime=8, packSize=100, minOrder=100,
         baseSales=16, salesStart=1.50, salesEnd=0.60, weekendFactor=0.90, seed=909,
         batches=[
             dict(code="CE-7702", qty=900, expires=100, arrived=85),
             dict(code="CE-7740", qty=1100, expires=410, arrived=30)]),
    dict(id="dro", name="Дротаверин", form="табл. 40 мг №20",
         priceIn=42, priceOut=89, leadTime=15, packSize=100, minOrder=100,
         baseSales=19, salesStart=1.00, salesEnd=1.02, weekendFactor=0.95, seed=1010,
         batches=[
             dict(code="DR-6604", qty=380, expires=310, arrived=45),
             dict(code="DR-6621", qty=240, expires=530, arrived=10)]),
]

# ------------------------------------------------------------------
# Утилиты
# ------------------------------------------------------------------
M32 = 0xFFFFFFFF


def mulberry32(seed):
    """Детерминированный ГПСЧ (тот же, что был в JS-версии)."""
    a = seed & M32

    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & M32
        t = ((a ^ (a >> 15)) * (1 | a)) & M32
        t = (((t + (((t ^ (t >> 7)) * (61 | t)) & M32)) & M32) ^ t)
        return ((t ^ (t >> 14)) & M32) / 4294967296

    return rnd


def js_round(x):
    return math.floor(x + 0.5)


def mean(a):
    return sum(a) / len(a) if a else 0.0


def day_to_date(today, n):
    return today + timedelta(days=n)


# ------------------------------------------------------------------
# История продаж и прогноз
# ------------------------------------------------------------------
def gen_sales(d, today):
    rnd = mulberry32(d["seed"])
    n = CFG["historyDays"]
    out = []
    for i in range(n - 1, -1, -1):          # i = «сколько дней назад»
        t = (n - 1 - i) / (n - 1)
        trend = d["salesStart"] + (d["salesEnd"] - d["salesStart"]) * t
        weekday = day_to_date(today, -i).weekday()   # Пн=0 … Вс=6
        weekly = d["weekendFactor"] if weekday >= 5 else 1
        noise = 0.85 + 0.30 * rnd()
        out.append(max(0, js_round(d["baseSales"] * trend * weekly * noise)))
    return out


def forecast_daily(sales):
    n = min(60, len(sales))
    y = sales[-n:]
    sx = sy = sxy = sxx = 0
    for i in range(n):
        sx += i
        sy += y[i]
        sxy += i * y[i]
        sxx += i * i
    denom = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / denom if denom else 0
    intercept = (sy - slope * sx) / n
    s = sum(max(0, intercept + slope * k) for k in range(n, n + 30))
    reg = s / 30
    avg14 = mean(y[-14:])
    return max(0.5, 0.75 * reg + 0.25 * avg14)


# ------------------------------------------------------------------
# FEFO-симуляция
# ------------------------------------------------------------------
def run_simulation(batches, rate, horizon):
    items = [dict(code=b["code"], lastDay=b["lastDay"], remaining=b["qty"],
                  sold=0.0, lost=0.0) for b in batches]
    sold = lost = shortage = 0.0
    eps = 1e-9

    for day in range(horizon):
        for it in items:                      # списание закрывшихся партий
            if it["remaining"] > eps and it["lastDay"] <= day:
                it["lost"] += it["remaining"]
                lost += it["remaining"]
                it["remaining"] = 0.0
        need = rate                           # продажи по FEFO
        avail = sorted((i for i in items if i["remaining"] > eps),
                       key=lambda i: i["lastDay"])
        for it in avail:
            if need <= eps:
                break
            take = min(it["remaining"], need)
            it["remaining"] -= take
            it["sold"] += take
            sold += take
            need -= take
        if need > eps:
            shortage += need
    return dict(items=items, sold=sold, lost=lost, shortage=shortage)


# ------------------------------------------------------------------
# Статусы
# ------------------------------------------------------------------
def status_of(d):
    if d["lossMoney"] > 15000 and d["overstock"]:
        return dict(text="Избыток + списание", cls="b-danger")
    if d["shortage"] > 0 and d["daysOfSupply"] < d["leadTime"] + 10:
        return dict(text="Дефицит", cls="b-danger")
    if d["lossQty"] > 0:
        return dict(text="Риск списания", cls="b-warn")
    if d["daysOfSupply"] > 120:
        return dict(text="Избыток", cls="b-warn")
    if d["shortage"] > 0:
        return dict(text="Дефицит", cls="b-danger")
    return dict(text="Норма", cls="b-ok")


# ------------------------------------------------------------------
# Построение модели
# ------------------------------------------------------------------
def build_model(msl, today=None):
    today = today or date.today()
    CFG["minShelfLifeDays"] = msl
    result = []

    for d in DRUGS_RAW:
        sales = gen_sales(d, today)
        forecast = forecast_daily(sales)

        batches = sorted(
            (dict(code=b["code"], qty=b["qty"], expiresInDays=b["expires"],
                  arrivedDaysAgo=b["arrived"],
                  expiryDate=day_to_date(today, b["expires"]).strftime("%d.%m.%Y"),
                  lastDay=b["expires"] - msl)
             for b in d["batches"]),
            key=lambda b: b["lastDay"])

        stock_total = sum(b["qty"] for b in batches)
        stock_sellable = sum(b["qty"] for b in batches if b["lastDay"] > 0)

        sim_full = run_simulation(batches, forecast, CFG["lossHorizonDays"])
        by_code = {i["code"]: i for i in sim_full["items"]}
        for b in batches:
            b["sold"] = by_code[b["code"]]["sold"]
            b["lost"] = by_code[b["code"]]["lost"]

        loss_qty = sim_full["lost"]
        loss_money = loss_qty * d["priceIn"]

        horizon = d["leadTime"] + CFG["planningDays"]
        sim_plan = run_simulation(batches, forecast, horizon)
        usable = sim_plan["sold"]
        demand = forecast * horizon * CFG["safetyFactor"]
        gap = max(0.0, demand - usable)
        overstock = stock_total > demand * 1.5

        order_qty = 0
        if not overstock and gap > 0:
            order_qty = math.ceil(gap / d["packSize"]) * d["packSize"]
            order_qty = max(order_qty, d["minOrder"])

        days_of_supply = stock_sellable / forecast if forecast > 0 else 9999

        item = dict(
            id=d["id"], name=d["name"], form=d["form"],
            priceIn=d["priceIn"], leadTime=d["leadTime"], packSize=d["packSize"],
            sales=sales, forecast=forecast,
            avg14=mean(sales[-14:]), avg28=mean(sales[-28:]),
            batches=batches,
            stockTotal=stock_total, stockSellable=stock_sellable,
            stockBlocked=stock_total - stock_sellable,
            lossQty=loss_qty, lossMoney=loss_money,
            shortage=sim_plan["shortage"], daysOfSupply=days_of_supply,
            horizon=horizon, demand=demand, usable=usable, gap=gap,
            overstock=overstock, orderQty=order_qty,
            orderValue=order_qty * d["priceIn"],
        )
        item["status"] = status_of(item)
        result.append(item)
    return result


# ------------------------------------------------------------------
# Маршруты
# ------------------------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html", allowed_msl=ALLOWED_MSL,
                           default_msl=CFG["minShelfLifeDays"])


@app.get("/api/model")
def api_model():
    msl = request.args.get("msl", default=60, type=int)
    if msl not in ALLOWED_MSL:
        return jsonify(error=f"msl должен быть одним из {list(ALLOWED_MSL)}"), 400
    today = date.today()
    return jsonify(
        today=today.strftime("%d.%m.%Y"),
        config={**CFG, "minShelfLifeDays": msl},
        drugs=build_model(msl, today),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
