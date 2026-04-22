-- ============================================================
-- AlphaBrief — Paper Portfolio Schema (Supabase) — Migration 001
-- À exécuter dans le SQL Editor du dashboard Supabase
-- Indépendant de supabase_schema.sql (extension)
-- ============================================================

-- ── 0. Fonction append-only partagée ────────────────────────
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table append-only: opération % interdite sur %',
        TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

-- ── 1. paper_portfolios ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS paper_portfolios (
    id              SMALLSERIAL PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL
                    CHECK (name IN ('TOP10','BOTTOM10','LONG_SHORT','SPY_BENCHMARK')),
    strategy        TEXT NOT NULL,
    initial_capital NUMERIC(14,2) NOT NULL CHECK (initial_capital > 0),
    started_at      DATE,  -- NULL tant que pas démarré (pas de backfill)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 2. paper_positions (état courant, mutable par design) ───
CREATE TABLE IF NOT EXISTS paper_positions (
    id           BIGSERIAL PRIMARY KEY,
    portfolio_id SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    ticker       TEXT NOT NULL,
    side         TEXT NOT NULL CHECK (side IN ('LONG','SHORT')),
    shares       NUMERIC(14,4) NOT NULL CHECK (shares > 0),
    entry_price  NUMERIC(12,4) NOT NULL CHECK (entry_price > 0),
    entry_date   DATE NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_paper_positions_portfolio
    ON paper_positions(portfolio_id);

-- ── 3. paper_rebalances ─── APPEND-ONLY + hash-chain ───────
CREATE TABLE IF NOT EXISTS paper_rebalances (
    id                BIGSERIAL PRIMARY KEY,
    portfolio_id      SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    rebalance_date    DATE NOT NULL,
    action            TEXT NOT NULL
                      CHECK (action IN ('BUY','SELL','SHORT','COVER','GENESIS')),
    ticker            TEXT NOT NULL,
    shares            NUMERIC(14,4) NOT NULL,
    price             NUMERIC(12,4) NOT NULL CHECK (price >= 0),
    fees              NUMERIC(10,4) NOT NULL DEFAULT 0 CHECK (fees >= 0),
    slippage          NUMERIC(10,4) NOT NULL DEFAULT 0 CHECK (slippage >= 0),
    score_at_decision INTEGER,
    rationale         TEXT,
    prev_hash         TEXT,                    -- NULL uniquement pour GENESIS
    row_hash          TEXT NOT NULL UNIQUE,    -- SHA256 canonique de la ligne
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_paper_rebalances_portfolio_date
    ON paper_rebalances(portfolio_id, rebalance_date DESC);
CREATE INDEX IF NOT EXISTS idx_paper_rebalances_date
    ON paper_rebalances(rebalance_date DESC);

CREATE TRIGGER tr_paper_rebalances_append_only
    BEFORE UPDATE OR DELETE ON paper_rebalances
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- ── 4. paper_nav_history ─── APPEND-ONLY ───────────────────
CREATE TABLE IF NOT EXISTS paper_nav_history (
    id                BIGSERIAL PRIMARY KEY,
    portfolio_id      SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    date              DATE NOT NULL,
    nav               NUMERIC(14,2) NOT NULL,
    cash_balance      NUMERIC(14,2) NOT NULL DEFAULT 0,
    cash_interest     NUMERIC(12,4) NOT NULL DEFAULT 0, -- intérêt SOFR du jour
    borrow_cost       NUMERIC(12,4) NOT NULL DEFAULT 0, -- coût emprunt shorts du jour
    daily_return      NUMERIC(10,6),
    cumulative_return NUMERIC(10,6),
    drawdown          NUMERIC(10,6),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, date)
);
CREATE INDEX IF NOT EXISTS idx_paper_nav_history_date
    ON paper_nav_history(date DESC);

CREATE TRIGGER tr_paper_nav_history_append_only
    BEFORE UPDATE OR DELETE ON paper_nav_history
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- ── 5. paper_metrics (mutable, recalculé quotidien) ────────
CREATE TABLE IF NOT EXISTS paper_metrics (
    portfolio_id SMALLINT PRIMARY KEY REFERENCES paper_portfolios(id),
    sharpe       NUMERIC(8,4),
    sortino      NUMERIC(8,4),
    max_drawdown NUMERIC(8,4),
    win_rate     NUMERIC(6,4),
    alpha_vs_spy NUMERIC(10,6),
    beta         NUMERIC(8,4),
    sample_days  INTEGER NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 6. paper_missed_rebalances ─── APPEND-ONLY ─────────────
CREATE TABLE IF NOT EXISTS paper_missed_rebalances (
    id             BIGSERIAL PRIMARY KEY,
    portfolio_id   SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    scheduled_date DATE NOT NULL,
    detected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason         TEXT NOT NULL
                   CHECK (reason IN ('VPS_DOWN','FMP_ERROR','SCORING_INCOMPLETE',
                                     'MANUAL_SKIP','UNKNOWN')),
    details        JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_paper_missed_portfolio_date
    ON paper_missed_rebalances(portfolio_id, scheduled_date DESC);

CREATE TRIGGER tr_paper_missed_rebalances_append_only
    BEFORE UPDATE OR DELETE ON paper_missed_rebalances
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- ── 7. paper_corporate_actions ─── APPEND-ONLY ─────────────
CREATE TABLE IF NOT EXISTS paper_corporate_actions (
    id             BIGSERIAL PRIMARY KEY,
    portfolio_id   SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    ticker         TEXT NOT NULL,
    action_type    TEXT NOT NULL
                   CHECK (action_type IN ('SPLIT','REVERSE_SPLIT','DIVIDEND',
                                          'SPINOFF','MERGER_CASH','MERGER_STOCK',
                                          'DELISTING','SUSPENSION')),
    effective_date DATE NOT NULL,
    details        JSONB NOT NULL DEFAULT '{}',
    applied_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_paper_corp_actions_ticker_date
    ON paper_corporate_actions(ticker, effective_date DESC);

CREATE TRIGGER tr_paper_corp_actions_append_only
    BEFORE UPDATE OR DELETE ON paper_corporate_actions
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- ── 8. paper_sofr_rates ─── APPEND-ONLY (fallback SOFR) ────
CREATE TABLE IF NOT EXISTS paper_sofr_rates (
    date       DATE PRIMARY KEY,
    rate       NUMERIC(8,5) NOT NULL,  -- taux annualisé décimal (ex: 0.04325)
    source     TEXT NOT NULL DEFAULT 'FMP',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER tr_paper_sofr_rates_append_only
    BEFORE UPDATE OR DELETE ON paper_sofr_rates
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- ============================================================
-- RLS : lecture publique sur TOUTES les tables paper_*
-- (c'est la preuve publique — l'écriture reste via service_role)
-- ============================================================
ALTER TABLE paper_portfolios          ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_positions           ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_rebalances          ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_nav_history         ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_metrics             ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_missed_rebalances   ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_corporate_actions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_sofr_rates          ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read paper_portfolios"
    ON paper_portfolios FOR SELECT USING (true);
CREATE POLICY "Public read paper_positions"
    ON paper_positions FOR SELECT USING (true);
CREATE POLICY "Public read paper_rebalances"
    ON paper_rebalances FOR SELECT USING (true);
CREATE POLICY "Public read paper_nav_history"
    ON paper_nav_history FOR SELECT USING (true);
CREATE POLICY "Public read paper_metrics"
    ON paper_metrics FOR SELECT USING (true);
CREATE POLICY "Public read paper_missed_rebalances"
    ON paper_missed_rebalances FOR SELECT USING (true);
CREATE POLICY "Public read paper_corporate_actions"
    ON paper_corporate_actions FOR SELECT USING (true);
CREATE POLICY "Public read paper_sofr_rates"
    ON paper_sofr_rates FOR SELECT USING (true);

-- Note : service_role bypasse RLS par design Supabase.
-- Les triggers append-only protègent l'immuabilité quel que soit
-- le rôle (y compris service_role).
