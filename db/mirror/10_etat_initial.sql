-- ============================================================
-- Base miroir — reconstitution du point de départ
-- ============================================================
-- Reproduit l'état de la base AVANT les migrations du pivot, tel qu'on
-- l'a constaté sur le projet Supabase réel le 2026-07-31 :
--
--   - ticker_scores, score_history et les 8 paper_* existent
--   - `alerts` N'EXISTE PAS, bien que supabase_schema.sql la décrive
--     (PGRST205 sur PostgREST). C'est volontairement reproduit ici :
--     c'est le cas qui fait échouer une migration naïve.
--   - les policies dangereuses sont posées à l'identique, y compris la
--     "Service write" sans clause TO qui ouvre l'écriture à anon
--
-- ⚠ RÉSERVE : les policies réelles n'ont pas pu être lues (pg_policies
--   n'est pas exposé par PostgREST). Ce fichier reflète les fichiers SQL
--   du repo, qui sont le meilleur modèle disponible, pas une capture.
--
-- Hors périmètre : profiles, watchlists, watchlist_tickers, ticker_events
-- existent en prod mais n'ont aucun DDL au repo et aucune migration ne
-- les touche.
-- ============================================================

-- ── Tables de scoring (supabase_schema.sql, SANS alerts) ────

CREATE TABLE IF NOT EXISTS ticker_scores (
    ticker           TEXT PRIMARY KEY,
    potential_score  INTEGER,
    confidence_score INTEGER,
    financials       JSONB DEFAULT '{}',
    valuation        JSONB DEFAULT '{}',
    market           JSONB DEFAULT '{}',
    identity         JSONB DEFAULT '{}',
    scored_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS score_history (
    id          BIGSERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL,
    score       INTEGER,
    confidence  INTEGER,
    recorded_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE ticker_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read ticker_scores"  ON ticker_scores;
DROP POLICY IF EXISTS "Public read score_history"  ON score_history;
DROP POLICY IF EXISTS "Service write ticker_scores" ON ticker_scores;
DROP POLICY IF EXISTS "Service write score_history" ON score_history;

CREATE POLICY "Public read ticker_scores" ON ticker_scores
    FOR SELECT USING (true);
CREATE POLICY "Public read score_history" ON score_history
    FOR SELECT USING (true);

-- LE TROU : FOR ALL sans clause TO → s'applique à `public`, donc à `anon`.
CREATE POLICY "Service write ticker_scores" ON ticker_scores
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service write score_history" ON score_history
    FOR ALL USING (true) WITH CHECK (true);

-- ── Tables paper_* (migration 001) ──────────────────────────

CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table append-only: opération % interdite sur %',
        TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS paper_portfolios (
    id              SMALLSERIAL PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    strategy        TEXT NOT NULL,
    initial_capital NUMERIC(14,2) NOT NULL CHECK (initial_capital > 0),
    started_at      DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS paper_positions (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    ticker TEXT NOT NULL, side TEXT NOT NULL,
    shares NUMERIC(14,4) NOT NULL, entry_price NUMERIC(12,4) NOT NULL,
    entry_date DATE NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, ticker)
);
CREATE TABLE IF NOT EXISTS paper_rebalances (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    rebalance_date DATE NOT NULL, action TEXT NOT NULL, ticker TEXT NOT NULL,
    shares NUMERIC(14,4) NOT NULL, price NUMERIC(12,4) NOT NULL,
    fees NUMERIC(10,4) NOT NULL DEFAULT 0, slippage NUMERIC(10,4) NOT NULL DEFAULT 0,
    score_at_decision INTEGER, rationale TEXT,
    prev_hash TEXT, row_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS paper_nav_history (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    date DATE NOT NULL, nav NUMERIC(14,2) NOT NULL,
    cash_balance NUMERIC(14,2) NOT NULL DEFAULT 0,
    cash_interest NUMERIC(12,4) NOT NULL DEFAULT 0,
    borrow_cost NUMERIC(12,4) NOT NULL DEFAULT 0,
    daily_return NUMERIC(10,6), cumulative_return NUMERIC(10,6),
    drawdown NUMERIC(10,6), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, date)
);
CREATE TABLE IF NOT EXISTS paper_metrics (
    portfolio_id SMALLINT PRIMARY KEY REFERENCES paper_portfolios(id),
    sharpe NUMERIC(8,4), sortino NUMERIC(8,4), max_drawdown NUMERIC(8,4),
    win_rate NUMERIC(6,4), alpha_vs_spy NUMERIC(10,6), beta NUMERIC(8,4),
    sample_days INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS paper_missed_rebalances (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    scheduled_date DATE NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason TEXT NOT NULL, details JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS paper_corporate_actions (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id SMALLINT NOT NULL REFERENCES paper_portfolios(id),
    ticker TEXT NOT NULL, action_type TEXT NOT NULL,
    effective_date DATE NOT NULL, details JSONB NOT NULL DEFAULT '{}',
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS paper_sofr_rates (
    date DATE PRIMARY KEY, rate NUMERIC(8,5) NOT NULL,
    source TEXT NOT NULL DEFAULT 'FMP',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['paper_portfolios','paper_positions','paper_rebalances',
                             'paper_nav_history','paper_metrics','paper_missed_rebalances',
                             'paper_corporate_actions','paper_sofr_rates']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', 'Public read ' || t, t);
        EXECUTE format('CREATE POLICY %I ON %I FOR SELECT USING (true)',
                       'Public read ' || t, t);
    END LOOP;
END $$;
