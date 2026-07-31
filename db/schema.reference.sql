-- ============================================================
-- AlphaBrief — RÉFÉRENCE DE SCHÉMA (constat, pas souhait)
-- ============================================================
-- Prise le    : 2026-07-31 23:28 UTC
-- Commit      : 60075bc
-- Source      : spec OpenAPI de PostgREST sur le projet Supabase
--
-- GÉNÉRÉ — ne pas éditer à la main. Regénérer avec :
--     python db/introspect.py --write
--
-- C'est CE fichier qui alimente la base miroir, plus
-- supabase_schema.sql. Un schéma écrit à la main dérive de la base
-- sans prévenir : c'est ce qui a coûté le bug `recorded_at`.
--
-- Vérifier la dérive à tout moment :  make db-drift
-- ============================================================

-- ── api_usage ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_usage (
    id          uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    user_id     uuid NOT NULL,
    date        date DEFAULT CURRENT_DATE NOT NULL,
    scan_count  integer DEFAULT '0' NOT NULL
);

-- ── paper_corporate_actions ─────────────────────────
CREATE TABLE IF NOT EXISTS paper_corporate_actions (
    id              bigint NOT NULL PRIMARY KEY,
    portfolio_id    smallint NOT NULL,
    ticker          text NOT NULL,
    action_type     text NOT NULL,
    effective_date  date NOT NULL,
    details         jsonb NOT NULL,
    applied_at      timestamp with time zone DEFAULT now() NOT NULL
);

-- ── paper_metrics ───────────────────────────────────
CREATE TABLE IF NOT EXISTS paper_metrics (
    portfolio_id  smallint NOT NULL PRIMARY KEY,
    sharpe        numeric,
    sortino       numeric,
    max_drawdown  numeric,
    win_rate      numeric,
    alpha_vs_spy  numeric,
    beta          numeric,
    sample_days   integer DEFAULT '0' NOT NULL,
    updated_at    timestamp with time zone DEFAULT now() NOT NULL
);

-- ── paper_missed_rebalances ─────────────────────────
CREATE TABLE IF NOT EXISTS paper_missed_rebalances (
    id              bigint NOT NULL PRIMARY KEY,
    portfolio_id    smallint NOT NULL,
    scheduled_date  date NOT NULL,
    detected_at     timestamp with time zone DEFAULT now() NOT NULL,
    reason          text NOT NULL,
    details         jsonb NOT NULL
);

-- ── paper_nav_history ───────────────────────────────
CREATE TABLE IF NOT EXISTS paper_nav_history (
    id                 bigint NOT NULL PRIMARY KEY,
    portfolio_id       smallint NOT NULL,
    date               date NOT NULL,
    nav                numeric NOT NULL,
    cash_balance       numeric DEFAULT '0' NOT NULL,
    cash_interest      numeric DEFAULT '0' NOT NULL,
    borrow_cost        numeric DEFAULT '0' NOT NULL,
    daily_return       numeric,
    cumulative_return  numeric,
    drawdown           numeric,
    created_at         timestamp with time zone DEFAULT now() NOT NULL
);

-- ── paper_portfolios ────────────────────────────────
CREATE TABLE IF NOT EXISTS paper_portfolios (
    id               smallint NOT NULL PRIMARY KEY,
    name             text NOT NULL,
    strategy         text NOT NULL,
    initial_capital  numeric NOT NULL,
    started_at       date,
    created_at       timestamp with time zone DEFAULT now() NOT NULL
);

-- ── paper_positions ─────────────────────────────────
CREATE TABLE IF NOT EXISTS paper_positions (
    id            bigint NOT NULL PRIMARY KEY,
    portfolio_id  smallint NOT NULL,
    ticker        text NOT NULL,
    side          text NOT NULL,
    shares        numeric NOT NULL,
    entry_price   numeric NOT NULL,
    entry_date    date NOT NULL,
    updated_at    timestamp with time zone DEFAULT now() NOT NULL
);

-- ── paper_rebalances ────────────────────────────────
CREATE TABLE IF NOT EXISTS paper_rebalances (
    id                 bigint NOT NULL PRIMARY KEY,
    portfolio_id       smallint NOT NULL,
    rebalance_date     date NOT NULL,
    action             text NOT NULL,
    ticker             text NOT NULL,
    shares             numeric NOT NULL,
    price              numeric NOT NULL,
    fees               numeric DEFAULT '0' NOT NULL,
    slippage           numeric DEFAULT '0' NOT NULL,
    score_at_decision  integer,
    rationale          text,
    prev_hash          text,
    row_hash           text NOT NULL,
    created_at         timestamp with time zone DEFAULT now() NOT NULL
);

-- ── paper_sofr_rates ────────────────────────────────
CREATE TABLE IF NOT EXISTS paper_sofr_rates (
    date        date NOT NULL PRIMARY KEY,
    rate        numeric NOT NULL,
    source      text DEFAULT 'FMP' NOT NULL,
    fetched_at  timestamp with time zone DEFAULT now() NOT NULL
);

-- ── profiles ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profiles (
    id                     uuid NOT NULL PRIMARY KEY,
    email                  text NOT NULL,
    plan                   text DEFAULT 'free' NOT NULL,
    stripe_customer_id     text,
    lemon_subscription_id  text,
    created_at             timestamp with time zone DEFAULT now() NOT NULL,
    updated_at             timestamp with time zone DEFAULT now() NOT NULL
);

-- ── score_history ───────────────────────────────────
CREATE TABLE IF NOT EXISTS score_history (
    id          bigint NOT NULL PRIMARY KEY,
    ticker      text NOT NULL,
    score       numeric NOT NULL,
    confidence  numeric DEFAULT '0' NOT NULL,
    scored_at   timestamp with time zone DEFAULT now() NOT NULL
);

-- ── ticker_events ───────────────────────────────────
CREATE TABLE IF NOT EXISTS ticker_events (
    id          bigint NOT NULL PRIMARY KEY,
    ticker      text NOT NULL,
    event_date  date NOT NULL,
    label       text NOT NULL,
    kind        text NOT NULL,
    source      text,
    created_at  timestamp with time zone DEFAULT now()
);

-- ── ticker_scores ───────────────────────────────────
CREATE TABLE IF NOT EXISTS ticker_scores (
    id                  uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    ticker              text NOT NULL,
    score_total         numeric NOT NULL,
    score_fundamentals  numeric NOT NULL,
    score_technicals    numeric NOT NULL,
    score_momentum      numeric NOT NULL,
    score_date          date DEFAULT CURRENT_DATE NOT NULL,
    computed_at         timestamp with time zone DEFAULT now() NOT NULL,
    company_name        text,
    sector              text,
    exchange            text,
    currency            text,
    market_cap          numeric,
    one_liner           text,
    moat_tags           jsonb,
    score_label         text,
    importance_items    jsonb,
    financials          jsonb,
    market_data         jsonb
);

-- ── user_scans ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_scans (
    id          uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    user_id     uuid NOT NULL,
    ticker      text NOT NULL,
    scanned_at  timestamp with time zone DEFAULT now() NOT NULL
);

-- ── watchlist_tickers ───────────────────────────────
CREATE TABLE IF NOT EXISTS watchlist_tickers (
    id            uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    watchlist_id  uuid NOT NULL,
    ticker        text NOT NULL,
    added_at      timestamp with time zone DEFAULT now() NOT NULL,
    created_at    timestamp with time zone DEFAULT now() NOT NULL
);

-- ── watchlists ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS watchlists (
    id          uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    user_id     uuid NOT NULL,
    name        text DEFAULT 'Ma watchlist' NOT NULL,
    created_at  timestamp with time zone DEFAULT now() NOT NULL
);
