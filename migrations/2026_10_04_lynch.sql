-- ============================================================
-- AlphaBrief — Catégories de Peter Lynch
-- Appliquée par `make db-apply` APRÈS la couche cycle.
-- ============================================================
--
-- Une grille de lecture, jamais un signal : le score n'en dépend pas.
-- Les règles (core/lynch/categories.py, versionnées) PROPOSENT une catégorie,
-- recalculée à chaque scoring ; une correction de Max (`lynch_source='manuel'`)
-- n'est jamais écrasée. Les définitions et seuils vivent dans le module, pas ici.
--
-- Idempotente : rejouable sans effet de bord (vérifié par `make db-reset`).
-- ============================================================

ALTER TABLE societes ADD COLUMN IF NOT EXISTS lynch_categorie  TEXT;
ALTER TABLE societes ADD COLUMN IF NOT EXISTS lynch_source     TEXT;         -- 'regles:v1' | 'manuel'
ALTER TABLE societes ADD COLUMN IF NOT EXISTS lynch_regle      TEXT;         -- la règle lisible qui a donné la catégorie
ALTER TABLE societes ADD COLUMN IF NOT EXISTS lynch_updated_at TIMESTAMPTZ;

-- Les six clés, et rien d'autre. Même liste que core/lynch/categories.py::KEYS —
-- un test le vérifie en lisant ce fichier.
ALTER TABLE societes DROP CONSTRAINT IF EXISTS societes_lynch_categorie_check;
ALTER TABLE societes ADD CONSTRAINT societes_lynch_categorie_check CHECK (
    lynch_categorie IS NULL OR lynch_categorie IN (
        'slow',
        'stalwart',
        'fast',
        'cyclical',
        'turnaround',
        'asset'
    )
);

-- Une catégorie posée est une catégorie sourcée et datée.
ALTER TABLE societes DROP CONSTRAINT IF EXISTS societes_lynch_trace_check;
ALTER TABLE societes ADD CONSTRAINT societes_lynch_trace_check CHECK (
    lynch_categorie IS NULL
    OR (lynch_source IS NOT NULL AND lynch_updated_at IS NOT NULL)
);
