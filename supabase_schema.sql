-- AlphaBrief — Schema Supabase
-- Exécuter dans le SQL Editor de Supabase Dashboard

-- 1. Table principale des scores (upsert par ticker)
CREATE TABLE IF NOT EXISTS ticker_scores (
    ticker TEXT PRIMARY KEY,
    potential_score INTEGER,
    confidence_score INTEGER,
    financials JSONB DEFAULT '{}',
    valuation JSONB DEFAULT '{}',
    market JSONB DEFAULT '{}',
    identity JSONB DEFAULT '{}',
    scored_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Historique des scores
CREATE TABLE IF NOT EXISTS score_history (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    score INTEGER,
    confidence INTEGER,
    recorded_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_score_history_ticker ON score_history(ticker);
CREATE INDEX IF NOT EXISTS idx_score_history_recorded ON score_history(recorded_at DESC);

-- 3. Alertes
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    prev_score INTEGER,
    new_score INTEGER,
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alerts(ticker);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);

-- 4. RLS — lecture publique (scores publics pour freemium)
ALTER TABLE ticker_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

-- Policy lecture publique
CREATE POLICY "Public read ticker_scores" ON ticker_scores
    FOR SELECT USING (true);

CREATE POLICY "Public read score_history" ON score_history
    FOR SELECT USING (true);

CREATE POLICY "Public read alerts" ON alerts
    FOR SELECT USING (true);

-- Policy écriture via service_role key (le backend utilise la clé secrète)
CREATE POLICY "Service write ticker_scores" ON ticker_scores
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service write score_history" ON score_history
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service write alerts" ON alerts
    FOR ALL USING (true) WITH CHECK (true);
