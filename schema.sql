-- Расширяем схему под функционал демо: категории, сезонность, сроки,
-- причины брака, отдельный период анализа.

DROP TABLE IF EXISTS sales, batches, drugs, settings CASCADE;

CREATE TABLE settings (
    id                INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    planning_days     INT           NOT NULL DEFAULT 30,
    safety_factor     NUMERIC(5,2)  NOT NULL DEFAULT 1.15,
    history_days      INT           NOT NULL DEFAULT 730,   -- 2 года истории
    analysis_days     INT           NOT NULL DEFAULT 365,   -- дефолт «1 год»
    block_percent     NUMERIC(4,2)  NOT NULL DEFAULT 0.60,  -- правило 60%
    season_threshold  NUMERIC(4,2)  NOT NULL DEFAULT 1.40,
    overstock_thresh  NUMERIC(4,2)  NOT NULL DEFAULT 1.50,
    tight_ratio       NUMERIC(4,2)  NOT NULL DEFAULT 0.90,
    warn_ratio        NUMERIC(4,2)  NOT NULL DEFAULT 1.30
);

CREATE TABLE drugs (
    id                SERIAL PRIMARY KEY,
    name              TEXT          NOT NULL,
    form              TEXT          NOT NULL,
    category          TEXT          NOT NULL,
    price_in          NUMERIC(12,2) NOT NULL,
    lead_time_days    INT           NOT NULL,
    pack_size         INT           NOT NULL DEFAULT 1,
    shelf_life_months INT           NOT NULL DEFAULT 24,
    trend             NUMERIC(6,3)  NOT NULL DEFAULT 0,
    season_profile    JSONB                                  -- {winter,spring,summer,autumn}
);

CREATE TABLE batches (
    id                SERIAL PRIMARY KEY,
    drug_id           INT  NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    code              TEXT NOT NULL,
    qty               INT  NOT NULL CHECK (qty >= 0),
    arrived_at        DATE NOT NULL,
    expires_at        DATE NOT NULL,
    recalled          BOOLEAN NOT NULL DEFAULT FALSE,
    storage_violation BOOLEAN NOT NULL DEFAULT FALSE,
    box_opened        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE sales (
    drug_id INT  NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
    sold_on DATE NOT NULL,
    qty     INT  NOT NULL,
    PRIMARY KEY (drug_id, sold_on)
);

CREATE INDEX idx_batches_drug_exp ON batches(drug_id, expires_at);
CREATE INDEX idx_sales_drug_date  ON sales(drug_id, sold_on);

INSERT INTO settings (id) VALUES (1);