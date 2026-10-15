"""Наполнение БД вымышленными данными.

Запуск:  python seed.py

Что делает:
  1. Очищает таблицы sales, batches, drugs.
  2. Вставляет 10 препаратов из прототипа.
  3. Вставляет партии.
  4. Генерирует 120 дней продаж той же логикой, что в прототипе
     (random.Random(seed)) — цифры совпадут с демкой.
"""
import asyncio
import random
from datetime import date, timedelta

from app import db_api
from app.config import DATABASE_URL


# ------------------------------------------------------------------
# Данные (скопированы из прототипа FastAPI)
# ------------------------------------------------------------------
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

HISTORY_DAYS = 120


# ------------------------------------------------------------------
# Генерация продаж (та же логика, что в прототипе)
# ------------------------------------------------------------------
def gen_sales(d, today: date) -> list[int]:
    rnd = random.Random(d["seed"])
    n = HISTORY_DAYS
    out = []
    for i in range(n - 1, -1, -1):                # i = «сколько дней назад»
        t = (n - 1 - i) / (n - 1)
        trend = d["salesStart"] + (d["salesEnd"] - d["salesStart"]) * t
        weekday = (today - timedelta(days=i)).weekday()
        weekly = d["weekendFactor"] if weekday >= 5 else 1
        noise = 0.85 + 0.30 * rnd.random()
        out.append(max(0, round(d["baseSales"] * trend * weekly * noise)))
    return out


# ------------------------------------------------------------------
# Сам сид
# ------------------------------------------------------------------
async def main():
    await db_api.init_pool(DATABASE_URL)

    print("Очистка таблиц...")
    await db_api.truncate_all()

    print("Вставка препаратов...")
    today = date.today()
    drug_id_by_slug: dict[str, int] = {}

    for d in DRUGS_RAW:
        new_id = await db_api.insert_drug({
            "name":           d["name"],
            "form":           d["form"],
            "price_in":       d["priceIn"],
            "price_out":      d["priceIn"] * 2,        # условно, для отображения
            "lead_time_days": d["leadTime"],
            "pack_size":      d["packSize"],
            "min_order_qty":  d["minOrder"],
            "base_sales":     d["baseSales"],
            "sales_start":    d["salesStart"],
            "sales_end":      d["salesEnd"],
            "weekend_factor": d["weekendFactor"],
            "rng_seed":       d["seed"],
        })
        drug_id_by_slug[d["id"]] = new_id
        print(f"  + {d['name']} (id={new_id})")

    print("Вставка партий...")
    batch_count = 0
    for d in DRUGS_RAW:
        drug_id = drug_id_by_slug[d["id"]]
        for b in d["batches"]:
            await db_api.insert_batch(drug_id, {
                "code":         b["code"],
                "qty_received": b["qty"],
                "qty_left":     b["qty"],
                "arrived_at":   today - timedelta(days=30),         # условно
                "expires_at":   today + timedelta(days=b["expires"]),
            })
            batch_count += 1
    print(f"  Всего партий: {batch_count}")

    print(f"Генерация истории продаж за {HISTORY_DAYS} дней...")
    sales_rows: list[tuple[int, date, int]] = []
    for d in DRUGS_RAW:
        drug_id = drug_id_by_slug[d["id"]]
        series = gen_sales(d, today)
        for i, qty in enumerate(series):
            sold_on = today - timedelta(days=(HISTORY_DAYS - 1 - i))
            sales_rows.append((drug_id, sold_on, qty))

    # вставка пачкой
    await db_api.insert_sales_bulk(sales_rows)
    print(f"  Всего записей: {len(sales_rows)}")

    await db_api.close_pool()
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())