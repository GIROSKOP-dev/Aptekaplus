"""Слой доступа к данным АптекаПлюс. Только чтение/запись, без расчётов."""
from __future__ import annotations
import json
from typing import Any, Optional
import asyncpg
from datetime import date as _date

_pool: Optional[asyncpg.Pool] = None





async def init_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> None:
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(
        dsn, min_size=min_size, max_size=max_size,
        command_timeout=30, 
    )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _p() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Пул не инициализирован. Вызови db_api.init_pool(dsn).")
    return _pool


# ------------------------------------------------------------------
# Настройки
# ------------------------------------------------------------------
async def get_settings() -> dict[str, Any]:
    async with _p().acquire() as c:
        row = await c.fetchrow("""
            SELECT planning_days, safety_factor::float8 AS safety_factor,
                   history_days, analysis_days, block_percent::float8 AS block_percent,
                   season_threshold::float8 AS season_threshold,
                   overstock_thresh::float8 AS overstock_thresh,
                   tight_ratio::float8 AS tight_ratio,
                   warn_ratio::float8 AS warn_ratio
            FROM settings WHERE id = 1
        """)
    return dict(row) if row else {}


# ------------------------------------------------------------------
# Препараты
# ------------------------------------------------------------------
async def get_drugs() -> list[dict[str, Any]]:
    async with _p().acquire() as c:
        rows = await c.fetch("""
            SELECT id, name, form, category,
                   price_in::float8 AS price_in,
                   lead_time_days, pack_size,
                   shelf_life_months, trend::float8 AS trend,
                   season_profile::text AS season_profile
            FROM drugs ORDER BY name
        """)
    out = []
    for r in rows:
        d = dict(r)
        sp = d.get("season_profile")
        d["season_profile"] = json.loads(sp) if sp else None
        out.append(d)
    return out


# ------------------------------------------------------------------
# Партии
# ------------------------------------------------------------------
async def get_batches() -> list[dict[str, Any]]:
    async with _p().acquire() as c:
        rows = await c.fetch("""
            SELECT id, drug_id, code, qty, arrived_at, expires_at,
                   recalled, storage_violation, box_opened
            FROM batches ORDER BY drug_id, expires_at
        """)
    return [dict(r) for r in rows]


# ------------------------------------------------------------------
# Продажи — одна функция вместо N запросов
# ------------------------------------------------------------------
async def get_all_sales(days: int) -> dict[int, list[int]]:
    async with _p().acquire() as c:
        rows = await c.fetch("""
            SELECT drug_id, qty FROM sales
            WHERE sold_on >= CURRENT_DATE - $1::int
            ORDER BY drug_id, sold_on
        """, days)
    out: dict[int, list[int]] = {}
    for r in rows:
        out.setdefault(r["drug_id"], []).append(r["qty"])
    return out


# ------------------------------------------------------------------
# Запись (для seed.py)
# ------------------------------------------------------------------
async def insert_drug(d: dict[str, Any]) -> int:
    async with _p().acquire() as c:
        return await c.fetchval("""
            INSERT INTO drugs (name, form, category, price_in,
                               lead_time_days, pack_size, shelf_life_months,
                               trend, season_profile)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
            RETURNING id
        """, d["name"], d["form"], d["category"], d["price_in"],
             d["lead_time_days"], d["pack_size"], d["shelf_life_months"],
             d["trend"],
             json.dumps(d["season_profile"]) if d.get("season_profile") else None)


async def insert_batch(drug_id: int, b: dict[str, Any]) -> int:
    async with _p().acquire() as c:
        return await c.fetchval("""
            INSERT INTO batches (drug_id, code, qty, arrived_at, expires_at,
                                 recalled, storage_violation, box_opened)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
        """, drug_id, b["code"], b["qty"], b["arrived_at"], b["expires_at"],
             b.get("recalled", False), b.get("storage_violation", False),
             b.get("box_opened", False))


async def insert_sales_bulk(rows: list[tuple[int, Any, int]]) -> None:
    async with _p().acquire() as c:
        await c.executemany("""
            INSERT INTO sales (drug_id, sold_on, qty) VALUES ($1,$2,$3)
            ON CONFLICT (drug_id, sold_on) DO UPDATE SET qty = EXCLUDED.qty
        """, rows)


async def truncate_all() -> None:
    async with _p().acquire() as c:
        await c.execute("TRUNCATE sales, batches, drugs RESTART IDENTITY CASCADE")

# ------------------------------------------------------------------
# Массовая замена из CSV
# ------------------------------------------------------------------
async def bulk_append_from_csv(
    drugs_csv: list[dict[str, Any]],
    batches_csv: list[dict[str, Any]],
) -> dict[str, int]:
    """Добавляет препараты и партии, не трогая существующие.

    Если препарат с таким же именем уже есть — переиспользуем его id
    (и не создаём дубль). Партии привязываются к существующему препарату.
    """
    from datetime import date as _date

    async with _p().acquire() as c:
        async with c.transaction():
            csv_to_db: dict[str, int] = {}
            added_drugs = 0
            reused_drugs = 0

            for d in drugs_csv:
                existing = await c.fetchval(
                    "SELECT id FROM drugs WHERE name = $1 LIMIT 1",
                    d["name"],
                )
                if existing is not None:
                    csv_to_db[d["csv_id"]] = existing
                    reused_drugs += 1
                    continue

                db_id = await c.fetchval("""
                    INSERT INTO drugs (name, form, category, price_in,
                                       lead_time_days, pack_size, shelf_life_months,
                                       trend, season_profile)
                    VALUES ($1,$2,$3,$4,$5,$6,$7, 0.03, NULL)
                    RETURNING id
                """, d["name"], d["form"], d["category"], d["price_in"],
                     d["lead_time_days"], d["pack_size"], d["shelf_life_months"])
                csv_to_db[d["csv_id"]] = db_id
                added_drugs += 1

            added_batches = 0
            skipped = 0
            for b in batches_csv:
                drug_id = csv_to_db.get(b["csv_drug_id"])
                if drug_id is None:
                    skipped += 1
                    continue

                try:
                    expiry_date = _date.fromisoformat(b["expiry"])
                except (ValueError, TypeError):
                    skipped += 1
                    continue

                # защита от дублей партий: код партии уникален у препарата
                exists = await c.fetchval(
                    "SELECT 1 FROM batches WHERE drug_id = $1 AND code = $2",
                    drug_id, b["code"],
                )
                if exists:
                    skipped += 1
                    continue

                await c.execute("""
                    INSERT INTO batches (drug_id, code, qty, arrived_at, expires_at,
                                         recalled, storage_violation, box_opened)
                    VALUES ($1,$2,$3, CURRENT_DATE, $4,$5,$6,$7)
                """, drug_id, b["code"], b["qty"], expiry_date,
                     b["recalled"], b["storage_violation"], b["box_opened"])
                added_batches += 1

            return {
                "drugs_added":    added_drugs,
                "drugs_reused":   reused_drugs,
                "batches_added":  added_batches,
                "batches_skipped": skipped,
            }