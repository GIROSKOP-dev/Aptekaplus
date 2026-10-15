"""Слой доступа к данным PharmaStock.

Только чтение/запись. Никаких расчётов — они в app/services/.
Бекендер импортирует этот модуль и вызывает async-функции.
"""
from __future__ import annotations

from typing import Any, Optional
import asyncpg

_pool: Optional[asyncpg.Pool] = None


# ------------------------------------------------------------------
# Жизненный цикл пула
# ------------------------------------------------------------------
async def init_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> None:
    """Создать пул. Вызывать один раз при старте приложения."""
    global _pool
    if _pool is not None:
        return
    _pool = await asyncpg.create_pool(
        dsn, min_size=min_size, max_size=max_size, command_timeout=30
    )


async def close_pool() -> None:
    """Закрыть пул. Вызывать при остановке приложения."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _p() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Пул не инициализирован. Вызови db.init_pool(dsn).")
    return _pool


# ------------------------------------------------------------------
# Настройки
# ------------------------------------------------------------------
async def get_settings() -> dict[str, Any]:
    """Все настройки одной строкой."""
    async with _p().acquire() as c:
        row = await c.fetchrow("""
            SELECT min_shelf_life_days,
                   loss_horizon_days,
                   planning_days,
                   safety_factor::float8 AS safety_factor,
                   history_days
            FROM settings WHERE id = 1
        """)
    return dict(row) if row else {}


async def update_min_shelf_life(days: int) -> None:
    async with _p().acquire() as c:
        await c.execute(
            "UPDATE settings SET min_shelf_life_days = $1 WHERE id = 1", days
        )


# ------------------------------------------------------------------
# Препараты
# ------------------------------------------------------------------
async def get_drugs() -> list[dict[str, Any]]:
    """Все препараты, без партий."""
    async with _p().acquire() as c:
        rows = await c.fetch("""
            SELECT id, name, form,
                   price_in::float8  AS price_in,
                   price_out::float8 AS price_out,
                   lead_time_days, pack_size, min_order_qty
            FROM drugs ORDER BY name
        """)
    return [dict(r) for r in rows]


async def get_drug(drug_id: int) -> Optional[dict[str, Any]]:
    async with _p().acquire() as c:
        row = await c.fetchrow("""
            SELECT id, name, form,
                   price_in::float8  AS price_in,
                   price_out::float8 AS price_out,
                   lead_time_days, pack_size, min_order_qty
            FROM drugs WHERE id = $1
        """, drug_id)
    return dict(row) if row else None


# ------------------------------------------------------------------
# Партии
# ------------------------------------------------------------------
async def get_batches(drug_id: Optional[int] = None) -> list[dict[str, Any]]:
    """Партии (все или одного препарата), отсортированы по сроку годности."""
    sql = """
        SELECT b.id, b.drug_id, b.code, b.qty_received, b.qty_left,
               b.arrived_at, b.expires_at,
               (b.expires_at - CURRENT_DATE) AS days_to_expiry
        FROM batches b
        {where}
        ORDER BY b.expires_at
    """.format(where="WHERE b.drug_id = $1" if drug_id is not None else "")
    async with _p().acquire() as c:
        rows = await c.fetch(sql, *([drug_id] if drug_id is not None else []))
    return [dict(r) for r in rows]


# ------------------------------------------------------------------
# Продажи
# ------------------------------------------------------------------
async def get_sales_series(drug_id: int, days: int) -> list[dict[str, Any]]:
    """Ряд продаж препарата за N последних дней: [{sold_on, qty}, ...]."""
    async with _p().acquire() as c:
        rows = await c.fetch("""
            SELECT sold_on, qty
            FROM sales
            WHERE drug_id = $1
              AND sold_on >= CURRENT_DATE - $2::int
            ORDER BY sold_on
        """, drug_id, days)
    return [dict(r) for r in rows]


async def get_all_sales(days: int) -> dict[int, list[int]]:
    """Все продажи за N дней: {drug_id: [qty, qty, ...]} по возрастанию даты.

    Одна функция вместо N запросов — для сборки модели целиком.
    """
    async with _p().acquire() as c:
        rows = await c.fetch("""
            SELECT drug_id, qty
            FROM sales
            WHERE sold_on >= CURRENT_DATE - $1::int
            ORDER BY drug_id, sold_on
        """, days)
    out: dict[int, list[int]] = {}
    for r in rows:
        out.setdefault(r["drug_id"], []).append(r["qty"])
    return out


# ------------------------------------------------------------------
# Сводка по складу — то, что рисует фронт первой вкладкой
# ------------------------------------------------------------------
async def get_stock_overview() -> list[dict[str, Any]]:
    """Препарат + суммарный остаток + ближайший срок годности."""
    async with _p().acquire() as c:
        rows = await c.fetch("""
            SELECT
                d.id, d.name, d.form,
                d.price_in::float8  AS price_in,
                d.price_out::float8 AS price_out,
                d.lead_time_days, d.pack_size, d.min_order_qty,
                COALESCE(SUM(b.qty_left), 0)::int AS stock_total,
                MIN(b.expires_at) AS nearest_expiry
            FROM drugs d
            LEFT JOIN batches b ON b.drug_id = d.id AND b.qty_left > 0
            GROUP BY d.id
            ORDER BY d.name
        """)
    return [dict(r) for r in rows]


# ------------------------------------------------------------------
# Запись (для seed.py)
# ------------------------------------------------------------------
async def insert_drug(d: dict[str, Any]) -> int:
    async with _p().acquire() as c:
        return await c.fetchval("""
            INSERT INTO drugs (name, form, price_in, price_out,
                               lead_time_days, pack_size, min_order_qty,
                               base_sales, sales_start, sales_end,
                               weekend_factor, rng_seed)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING id
        """,
            d["name"], d["form"], d["price_in"], d["price_out"],
            d["lead_time_days"], d["pack_size"], d["min_order_qty"],
            d["base_sales"], d["sales_start"], d["sales_end"],
            d["weekend_factor"], d["rng_seed"],
        )


async def insert_batch(drug_id: int, b: dict[str, Any]) -> int:
    async with _p().acquire() as c:
        return await c.fetchval("""
            INSERT INTO batches (drug_id, code, qty_received, qty_left,
                                 arrived_at, expires_at)
            VALUES ($1,$2,$3,$4,$5,$6)
            RETURNING id
        """,
            drug_id, b["code"], b["qty_received"], b["qty_left"],
            b["arrived_at"], b["expires_at"],
        )


async def insert_sales_bulk(rows: list[tuple[int, Any, int]]) -> None:
    """rows = [(drug_id, sold_on, qty), ...] — пачкой."""
    async with _p().acquire() as c:
        await c.executemany("""
            INSERT INTO sales (drug_id, sold_on, qty)
            VALUES ($1,$2,$3)
            ON CONFLICT (drug_id, sold_on) DO UPDATE SET qty = EXCLUDED.qty
        """, rows)


async def truncate_all() -> None:
    """Очистить все данные (перед пересевом)."""
    async with _p().acquire() as c:
        await c.execute("TRUNCATE sales, batches, drugs RESTART IDENTITY CASCADE")