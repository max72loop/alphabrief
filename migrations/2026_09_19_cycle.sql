-- ============================================================
-- AlphaBrief — Couche « phase de cycle »
-- Appliquée par `make db-apply` APRÈS db/schema.sql et le lot 1.
-- ============================================================
--
-- Deux objets, et rien qui décide :
--   1. societes.secteur_gics — la classification GICS des sociétés suivies,
--      alimentée par la fiche (identité FMP, complétée yfinance) et jamais
--      écrasée une fois posée. La TABLE secteur → phase n'est PAS ici : elle
--      vit dans core/cycle/mapping.py, versionnée et diffable.
--   2. cycle_phase_declarations — la phase DÉCLARÉE par Max, datée. Journal
--      en ajout seul : la dernière ligne fait foi, l'historique reste lisible.
--      « Une phase non datée est une phase fausse » : declared_at NOT NULL.
--
-- Idempotente : rejouable sans effet de bord (vérifié par `make db-reset`,
-- qui rejoue tout deux fois).
-- ============================================================


-- ── 1. societes.secteur_gics ────────────────────────────────

ALTER TABLE societes ADD COLUMN IF NOT EXISTS secteur_gics       TEXT;
ALTER TABLE societes ADD COLUMN IF NOT EXISTS secteur_source     TEXT;         -- 'fmp' | 'yf-direct' | 'fmp+yf' | 'manuel'
ALTER TABLE societes ADD COLUMN IF NOT EXISTS secteur_updated_at TIMESTAMPTZ;

-- Les onze secteurs GICS, et rien d'autre : un libellé fournisseur non
-- normalisé (« Consumer Cyclical ») ne doit pas pouvoir entrer. La liste est
-- la même que core/cycle/mapping.py::SECTORS — un test le vérifie en lisant
-- ce fichier. DROP + ADD plutôt qu'un DO $$ … $$ : c'est ce qui rend la
-- contrainte rejouable ET modifiable par simple réédition de la liste.
ALTER TABLE societes DROP CONSTRAINT IF EXISTS societes_secteur_gics_check;
ALTER TABLE societes ADD CONSTRAINT societes_secteur_gics_check CHECK (
    secteur_gics IS NULL OR secteur_gics IN (
        'Consumer Discretionary',
        'Financials',
        'Real Estate',
        'Industrials',
        'Information Technology',
        'Communication Services',
        'Energy',
        'Materials',
        'Health Care',
        'Consumer Staples',
        'Utilities'
    )
);

-- Un secteur posé est un secteur sourcé et daté.
ALTER TABLE societes DROP CONSTRAINT IF EXISTS societes_secteur_trace_check;
ALTER TABLE societes ADD CONSTRAINT societes_secteur_trace_check CHECK (
    secteur_gics IS NULL
    OR (secteur_source IS NOT NULL AND secteur_updated_at IS NOT NULL)
);


-- ── 2. cycle_phase_declarations ─────────────────────────────

CREATE TABLE IF NOT EXISTS cycle_phase_declarations (
    id          BIGSERIAL PRIMARY KEY,
    phase       TEXT NOT NULL
                CHECK (phase IN ('recovery','expansion','slowdown','recession')),
    declared_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cycle_phase_declared_at
    ON cycle_phase_declarations(declared_at DESC);
