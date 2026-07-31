-- AlphaBrief — Schéma Supabase (état constaté)
--
-- ⚠ Ce fichier décrivait jusqu'au 2026-07-31 une v1 obsolète : un
--   ticker_scores à (potential_score, confidence_score, valuation, market,
--   identity, scored_at) qui n'existe plus, et un score_history en
--   `recorded_at` là où la table déployée utilise `scored_at`. C'est cette
--   dérive qui faisait échouer en silence chaque insert d'historique.
--
--   Il est désormais aligné sur la base réelle, introspectée via PostgREST.
--   Ne pas le modifier sans vérifier la base : c'est un constat, pas un
--   souhait.
--
-- ⚠ `alerts` figurait ici mais n'a jamais été créée dans le projet
--   (PGRST205). Elle est retirée plutôt que laissée à décrire une table
--   fantôme. La feature d'alertes est à trancher au lot 4 : créer la table,
--   ou retirer la surface côté frontend et daemon.

-- ── 1. ticker_scores — écrite par le daemon (service_role) ──
CREATE TABLE IF NOT EXISTS ticker_scores (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker             TEXT UNIQUE NOT NULL,
    company_name       TEXT,
    sector             TEXT,
    exchange           TEXT,
    currency           TEXT,
    market_cap         BIGINT,
    one_liner          TEXT,
    moat_tags          JSONB DEFAULT '[]',
    score_total        INTEGER,
    score_fundamentals INTEGER,
    score_technicals   INTEGER,
    score_momentum     INTEGER,
    score_label        TEXT,
    importance_items   JSONB DEFAULT '[]',
    financials         JSONB DEFAULT '{}',
    market_data        JSONB DEFAULT '{}',
    score_date         DATE,
    computed_at        TIMESTAMPTZ DEFAULT now()
);

-- ── 2. score_history — la colonne est scored_at ─────────────
CREATE TABLE IF NOT EXISTS score_history (
    id         BIGSERIAL PRIMARY KEY,
    ticker     TEXT NOT NULL,
    score      INTEGER,
    confidence INTEGER,
    scored_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_score_history_ticker ON score_history(ticker);
CREATE INDEX IF NOT EXISTS idx_score_history_scored ON score_history(scored_at DESC);

-- ── 3. RLS ──────────────────────────────────────────────────
-- Les policies vivent dans migrations/2026_07_31_close_public_rls.sql.
-- Ce fichier ne décrit plus que la structure : la sécurité a un seul
-- endroit, versionné et testé sur la base miroir.
--
-- Rappel du partage cible :
--   ticker_scores, score_history               -> authenticated LIT, service_role ÉCRIT
--   supports/positions/snapshots/flux/societes -> authenticated LIT ET ÉCRIT
