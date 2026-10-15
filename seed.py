"""Заполнить БД демо-данными (эквивалент data.js)."""
import asyncio
import json
import random
from datetime import date, timedelta

from app import db_api
from app.config import DATABASE_URL

# ── Ключевой момент ─────────────────────────────────────────────────
DEMO_TODAY = date(2025, 2, 15)      # дата, на которую рассчитаны DRUGS ниже
REAL_TODAY = date.today()           # реальная сегодня
SHIFT = (REAL_TODAY - DEMO_TODAY).days

def _shift(iso: str) -> date:
    """Сдвинуть демо-дату на SHIFT, чтобы она была «относительно сегодня»."""
    return date.fromisoformat(iso) + timedelta(days=SHIFT)
# ────────────────────────────────────────────────────────────────────

SEASON_MONTHS = {
    "winter": (12, 1, 2), "spring": (3, 4, 5),
    "summer": (6, 7, 8), "autumn": (9, 10, 11),
}

# ---- препараты ------------------------------------------------------------
# batches: (code, qty, expires_at, flags)   flags = {} | {"recalled":True} | {"storage_violation":True} | {"box_opened":True}
DRUGS = [
    ("Амоксициллин 500 мг","таб. №20","Антибиотики",20,145,14,24,0.08,
     {"winter":1.5,"spring":1.0,"summer":0.6,"autumn":1.3},14,
     [("AMX-2401",180,"2025-04-10",{}),
      ("AMX-2402",320,"2025-11-15",{}),
      ("AMX-2403",400,"2026-08-15",{})]),

    ("Азитромицин 500 мг","таб. №3","Антибиотики",3,320,18,24,0.10,
     {"winter":1.65,"spring":0.85,"summer":0.65,"autumn":1.15},4,
     [("AZI-2311",45,"2025-05-20",{}),
      ("AZI-2401",120,"2026-03-10",{}),
      ("AZI-2402",140,"2026-12-01",{"recalled":True})]),        # ← флаг вернулся на AZI-2402

    ("Кларитромицин 500 мг","таб. №14","Антибиотики",14,340,14,24,0.06,
     {"winter":1.45,"spring":0.95,"summer":0.6,"autumn":1.25},7,
     [("KR-2401",80,"2025-07-01",{}),
      ("KR-2402",160,"2026-06-15",{})]),

    ("Цефтриаксон 1 г","порошок","Антибиотики",1,180,12,24,0.05,
     {"winter":1.4,"spring":1.0,"summer":0.7,"autumn":1.2},6,
     [("CF-2401",150,"2025-10-01",{}),
      ("CF-2402",200,"2026-09-01",{})]),

    ("Парацетамол 500 мг","таб. №20","Анальгетики",20,65,7,36,0.02,
     {"winter":1.15,"spring":0.95,"summer":0.85,"autumn":1.05},22,
     [("PCM-2311",60,"2025-04-15",{}),
      ("PCM-2401",450,"2026-06-15",{}),
      ("PCM-2402",600,"2027-08-15",{}),
      ("PCM-2403",400,"2028-01-15",{})]),

    ("Ибупрофен 400 мг","таб. №50","НПВС",50,210,10,24,-0.05,
     {"winter":1.2,"spring":1.1,"summer":1.3,"autumn":0.95},8,
     [("IBU-2312",95,"2025-04-05",{}),
      ("IBU-2401",280,"2026-01-10",{"box_opened":True}),
      ("IBU-2402",220,"2026-11-01",{})]),

    ("Дротаверин 40 мг","таб. №20","Спазмолитики",20,80,9,36,0.03,
     {"winter":1.0,"spring":1.05,"summer":1.0,"autumn":0.95},10,
     [("DR-2401",400,"2026-12-01",{}),
      ("DR-2402",500,"2027-10-01",{})]),

    ("Омепразол 20 мг","капс. №30","ЖКТ",30,180,21,24,0.04,
     {"winter":1.1,"spring":1.05,"summer":0.9,"autumn":1.0},6,
     [("OMP-2312",210,"2025-05-01",{}),
      ("OMP-2401",180,"2026-02-20",{}),
      ("OMP-2402",250,"2026-11-10",{})]),

    ("Смекта 3 г","порошок №10","ЖКТ",10,190,8,36,0.02,
     {"winter":1.15,"spring":1.05,"summer":1.45,"autumn":1.0},9,
     [("SM-2401",220,"2027-06-01",{}),
      ("SM-2402",150,"2028-04-01",{})]),

    ("Регидрон","порошок №1","ЖКТ",1,65,9,36,0.04,
     {"winter":0.5,"spring":0.9,"summer":2.3,"autumn":1.0},8,
     [("RG-2401",800,"2027-12-01",{}),
      ("RG-2402",500,"2028-10-01",{})]),

    ("Осельтамивир 75 мг","капс. №10","Противовирусные",10,890,14,24,0.12,
     {"winter":4.5,"spring":0.6,"summer":0.15,"autumn":1.2},1.2,
     [("OS-2401",180,"2026-06-01",{}),
      ("OS-2402",120,"2027-02-15",{})]),

    ("Ремантадин 50 мг","таб. №20","Противовирусные",20,145,10,24,0.08,
     {"winter":3.5,"spring":0.7,"summer":0.2,"autumn":1.1},4,
     [("RM-2401",500,"2026-07-01",{}),
      ("RM-2402",320,"2027-03-01",{})]),

    ("Аскорбиновая кислота 500 мг","таб. №10","Витамины",10,40,9,24,-0.12,
     {"winter":1.8,"spring":1.25,"summer":0.7,"autumn":1.05},18,
     [("ASC-2308",800,"2025-04-10",{}),
      ("ASC-2401",1200,"2026-05-10",{}),
      ("ASC-2402",900,"2027-02-15",{})]),

    ("Цинк + витамин C","шипучие №20","Витамины",20,78,9,24,0.05,
     {"winter":1.9,"spring":1.3,"summer":0.6,"autumn":1.1},9,
     [("ZC-2401",1200,"2026-04-01",{}),
      ("ZC-2402",700,"2027-02-01",{})]),

    ("Лоратадин 10 мг","таб. №10","Антигистамины",10,55,12,24,-0.08,
     {"winter":0.45,"spring":1.75,"summer":1.15,"autumn":0.65},3,
     [("LOR-2309",340,"2025-04-01",{}),
      ("LOR-2401",500,"2026-03-05",{}),
      ("LOR-2402",280,"2027-02-10",{})]),

    ("Цетиризин-капли","фл. 10 мл","Антигистамины",1,95,6,24,0.02,
     {"winter":0.35,"spring":2.1,"summer":1.25,"autumn":0.55},6,
     [("CK-2401",700,"2026-05-01",{}),
      ("CK-2402",450,"2027-04-15",{})]),

    ("Мометазон спрей","фл. 120 доз","Антигистамины",1,420,12,24,0.06,
     {"winter":0.5,"spring":2.3,"summer":1.15,"autumn":0.7},3,
     [("MN-2401",380,"2026-07-01",{}),
      ("MN-2402",220,"2027-02-20",{})]),

    ("Амброксол 30 мг","таб. №20","Дыхательная",20,52,7,24,0.03,
     {"winter":1.65,"spring":1.05,"summer":0.45,"autumn":1.45},6,
     [("AB-2309",720,"2026-04-01",{}),
      ("AB-2310",540,"2027-02-15",{})]),

    ("Ксилометазолин 0.1%","спрей 10 мл","Дыхательная",1,48,6,24,0.04,
     {"winter":2.0,"spring":0.85,"summer":0.4,"autumn":1.25},10,
     [("XS-2401",1400,"2026-07-01",{}),
      ("XS-2402",900,"2027-05-01",{})]),

    ("АЦЦ 200 мг","шипучие №20","Дыхательная",20,145,7,24,0.02,
     {"winter":1.6,"spring":1.0,"summer":0.5,"autumn":1.5},5,
     [("ACC-2401",580,"2026-06-01",{}),
      ("ACC-2402",350,"2027-03-15",{"storage_violation":True})]),

    ("Метформин 1000 мг","таб. №60","Диабет",60,260,20,24,0.03,None,11,
     [("MET-2312",240,"2025-10-15",{}),
      ("MET-2401",360,"2026-10-01",{})]),

    ("Эналаприл 10 мг","таб. №20","Кардио",20,48,11,36,0.02,None,9,
     [("EN-2401",1400,"2027-07-01",{}),
      ("EN-2402",900,"2028-02-01",{})]),
]


# ---- генерация продаж -----------------------------------------------------
def _season_factor(profile, d):
    if not profile:
        return 1.0
    for s, months in SEASON_MONTHS.items():
        if d.month in months:
            return profile.get(s, 1.0)
    return 1.0


def _gen_sales(base, trend, profile, days, seed):
    rng = random.Random(seed)
    out = []
    for i in range(days):
        d = REAL_TODAY - timedelta(days=days - 1 - i)   # ← было TODAY
        season = _season_factor(profile, d)
        trend_part = base * (1 + trend * (i / 365))
        noise = (rng.random() - 0.5) * 0.15 * base
        out.append(max(0.5, round((trend_part + noise) * season, 1)))
    return out


# ---- main -----------------------------------------------------------------
async def main():
    await db_api.init_pool(DATABASE_URL)
    try:
        await db_api.truncate_all()
        s = await db_api.get_settings()
        history_days = s["history_days"]

        for idx, (name, form, cat, pack, price, lead, shelf,
                  trend, prof, base, batches) in enumerate(DRUGS, 1):

            drug_id = await db_api.insert_drug({
                "name": name, "form": form, "category": cat,
                "price_in": price, "lead_time_days": lead,
                "pack_size": pack, "shelf_life_months": shelf,
                "trend": trend,
                "season_profile": prof,
            })

            for code, qty, exp, flags in batches:
                await db_api.insert_batch(drug_id, {
                    "code": code, "qty": qty,
                    "arrived_at":   REAL_TODAY - timedelta(days=180),
                    "expires_at":   _shift(exp),                # ← сдвинули
                    "recalled":          bool(flags.get("recalled", False)),
                    "storage_violation": bool(flags.get("storage_violation", False)),
                    "box_opened":        bool(flags.get("box_opened", False)),
                })

            # история продаж — тоже относительно REAL_TODAY
            sales = _gen_sales(base, trend, prof, history_days, seed=100 + idx)
            rows = [
                (drug_id, REAL_TODAY - timedelta(days=history_days - 1 - i), int(round(v)))
                for i, v in enumerate(sales)
            ]
            await db_api.insert_sales_bulk(rows)
            print(f"✓ {name}: {len(batches)} партий, {len(sales)} дн. продаж")
        print("Готово.")
    finally:
        await db_api.close_pool()


if __name__ == "__main__":
    asyncio.run(main())