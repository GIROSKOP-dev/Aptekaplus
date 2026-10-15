-- PharmaStock — схема БД
-- Применение:  psql -U pharma -d pharmastock -f schema.sql
--
-- Файл пересоздаёт таблицы с нуля (DROP + CREATE).
-- Это удобно во время разработки — можно безопасно перезапускать.
-- НЕ применять на боевой базе.

DROP TABLE IF EXISTS sales   CASCADE;
DROP TABLE IF EXISTS batches CASCADE;
DROP TABLE IF EXISTS drugs   CASCADE;
DROP TABLE IF EXISTS settings CASCADE;

-- ------------------------------------------------------------------
-- Препараты (справочник)
-- ------------------------------------------------------------------
CREATE TABLE drugs (
    id              SERIAL PRIMARY KEY,
    name            TEXT          NOT NULL,
    form            TEXT          NOT NULL,
    price_in        NUMERIC(10,2) NOT NULL CHECK (price_in  >= 0),
    price_out       NUMERIC(10,2) NOT NULL CHECK (price_out >= 0),
    lead_time_days  INT           NOT NULL CHECK (lead_time_days  > 0),
    pack_size       INT           NOT NULL CHECK (pack_size       > 0),
    min_order_qty   INT           NOT NULL CHECK (min_order_qty   > 0),

    -- параметры для сида истории продаж
    base_sales      NUMERIC(6,2)  NOT NULL CHECK (base_sales   >= 0),
    sales_start     NUMERIC(4,2)  NOT NULL CHECK (sales_start  >  0),
    sales_end       NUMERIC(4,2)  NOT NULL CHECK (sales_end    >  0),
    weekend_factor  NUMERIC(4,2)  NOT NULL CHECK (weekend_factor BETWEEN 0 AND 1),
    rng_seed        INT           NOT NULL
);

-- ------------------------------------------------------------------
-- Партии на складе
-- ------------------------------------------------------------------
CREATE TABLE batches (
    id            SERIAL PRIMARY KEY,
    drug_id       INT  NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    code          TEXT NOT NULL,
    qty_received  INT  NOT NULL CHECK (qty_received > 0),
    qty_left      INT  NOT NULL CHECK (qty_left    >= 0),
    arrived_at    DATE NOT NULL,
    expires_at    DATE NOT NULL,
    CHECK (expires_at > arrived_at)
);

CREATE INDEX idx_batches_drug    ON batches(drug_id);
CREATE INDEX idx_batches_expires ON batches(expires_at);

-- ------------------------------------------------------------------
-- История продаж (по дням, агрегированно по препарату)
-- ------------------------------------------------------------------
CREATE TABLE sales (
    id        BIGSERIAL PRIMARY KEY,
    drug_id   INT  NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    sold_on   DATE NOT NULL,
    qty       INT  NOT NULL CHECK (qty >= 0),
    UNIQUE (drug_id, sold_on)
);

CREATE INDEX idx_sales_drug_date ON sales(drug_id, sold_on);

-- ------------------------------------------------------------------
-- Настройки (одна строка, id всегда = 1)
-- ------------------------------------------------------------------
CREATE TABLE settings (
    id                    INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    min_shelf_life_days   INT           NOT NULL DEFAULT 60  CHECK (min_shelf_life_days > 0),
    loss_horizon_days     INT           NOT NULL DEFAULT 180 CHECK (loss_horizon_days   > 0),
    planning_days         INT           NOT NULL DEFAULT 30  CHECK (planning_days       > 0),
    safety_factor         NUMERIC(4,2)  NOT NULL DEFAULT 1.15 CHECK (safety_factor     >= 1),
    history_days          INT           NOT NULL DEFAULT 120 CHECK (history_days        > 0)
);

INSERT INTO settings (id) VALUES (1) ON CONFLICT DO NOTHING;