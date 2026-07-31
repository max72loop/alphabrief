-- ============================================================
-- AlphaBrief — Lot 1 : schéma patrimoine personnel
-- À exécuter dans le SQL Editor du dashboard Supabase
-- APRÈS 2026_07_31_close_public_rls.sql
-- ============================================================
--
-- 5 tables : supports, positions, snapshots, flux, societes.
-- Mono-utilisateur : aucune colonne user_id. L'isolation vient de l'auth
-- Supabase + RLS `authenticated`, pas d'un discriminant par ligne.
--
-- Devise de référence EUR. Chaque montant est stocké dans sa devise native
-- avec le taux appliqué, et la valeur EUR est dérivée — jamais saisie.
--
-- Idempotente : rejouable sans effet de bord.
-- ============================================================


-- ── 0. Helper updated_at ────────────────────────────────────

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ── 1. supports ─────────────────────────────────────────────
-- Les 4 supports réels : Bitpanda, Revolut, Trade Republic, Ledger.
--
-- `classe_dominante` sert au dashboard : un snapshot de niveau support ne
-- porte qu'un montant total, sans détail par classe d'actif. Sans cette
-- colonne, la répartition « actions / crypto / cash » serait impossible pour
-- un support saisi globalement (le cas nominal). Laisser NULL sur un support
-- réellement mixte : ses montants seront alors classés « indetermine ».

CREATE TABLE IF NOT EXISTS supports (
    id               BIGSERIAL PRIMARY KEY,
    nom              TEXT NOT NULL UNIQUE,
    type             TEXT NOT NULL
                     CHECK (type IN ('exchange','broker','cold_wallet')),
    devise           TEXT NOT NULL DEFAULT 'EUR',
    classe_dominante TEXT
                     CHECK (classe_dominante IN ('actions','crypto','cash')),
    actif            BOOLEAN NOT NULL DEFAULT true,
    ordre            SMALLINT NOT NULL DEFAULT 0,  -- ordre d'affichage sur l'écran de saisie
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_supports_touch ON supports;
CREATE TRIGGER tr_supports_touch BEFORE UPDATE ON supports
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- ── 2. positions ────────────────────────────────────────────
-- Une ligne détenue sur un support. Le détail par position est OPTIONNEL :
-- on peut très bien n'avoir que des snapshots de niveau support.

CREATE TABLE IF NOT EXISTS positions (
    id          BIGSERIAL PRIMARY KEY,
    support_id  BIGINT NOT NULL REFERENCES supports(id) ON DELETE CASCADE,
    actif       TEXT NOT NULL,          -- ticker actions ou symbole crypto (BTC, ETH…)
    libelle     TEXT,                   -- nom lisible si le symbole est opaque
    classe      TEXT NOT NULL
                CHECK (classe IN ('actions','crypto','cash')),
    devise      TEXT NOT NULL DEFAULT 'EUR',
    notes       TEXT,                   -- markdown, libre
    ouverte     BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (support_id, actif)
);

CREATE INDEX IF NOT EXISTS idx_positions_support ON positions(support_id);
CREATE INDEX IF NOT EXISTS idx_positions_actif   ON positions(actif);

DROP TRIGGER IF EXISTS tr_positions_touch ON positions;
CREATE TRIGGER tr_positions_touch BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- ── 3. snapshots ────────────────────────────────────────────
-- DOUBLE NIVEAU, exactement l'un des deux :
--   support_id  → valeur totale du support (flux nominal, 1 chiffre/semaine)
--   position_id → détail d'une ligne (optionnel, ponctuel)
--
-- ⚠ RÈGLE DE NON-DOUBLE-COMPTAGE, à respecter côté lecture :
--   le total d'un support à une date est le snapshot de NIVEAU SUPPORT.
--   Les snapshots de niveau position sont du DÉTAIL : ils ne s'additionnent
--   jamais dans le total patrimonial. Si seul le détail existe pour une date,
--   c'est au lot 3 de décider d'agréger — la base ne le présume pas.
--
-- valeur_eur est dérivée, jamais saisie : c'est la contrainte « devise de
-- référence EUR, conversion au taux du jour » rendue non contournable.

CREATE TABLE IF NOT EXISTS snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    support_id          BIGINT REFERENCES supports(id)  ON DELETE CASCADE,
    position_id         BIGINT REFERENCES positions(id) ON DELETE CASCADE,
    date                DATE NOT NULL,
    quantite            NUMERIC(28,10),          -- NULL au niveau support
    valeur              NUMERIC(16,2) NOT NULL CHECK (valeur >= 0),
    devise              TEXT NOT NULL DEFAULT 'EUR',
    taux_eur            NUMERIC(20,10) NOT NULL DEFAULT 1 CHECK (taux_eur > 0),
    valeur_eur          NUMERIC(18,4)
                        GENERATED ALWAYS AS (valeur * taux_eur) STORED,
    source              TEXT NOT NULL DEFAULT 'manuelle'
                        CHECK (source IN ('manuelle','api')),
    is_opening_position BOOLEAN NOT NULL DEFAULT false,
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT snapshot_cible_exclusive
        CHECK (num_nonnulls(support_id, position_id) = 1)
);

-- Un seul snapshot par cible et par date — l'écran de saisie fait un upsert
-- dessus, corriger une valeur ne crée pas de doublon.
CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_support_date
    ON snapshots(support_id, date)  WHERE support_id  IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_position_date
    ON snapshots(position_id, date) WHERE position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(date DESC);


-- ── 4. flux ─────────────────────────────────────────────────
-- Apports et retraits, au niveau support. C'est le seul dénominateur de la
-- performance : perf = valeur actuelle − (apports − retraits).
-- Montant toujours positif, le sens porte la direction.

CREATE TABLE IF NOT EXISTS flux (
    id          BIGSERIAL PRIMARY KEY,
    support_id  BIGINT NOT NULL REFERENCES supports(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    montant     NUMERIC(16,2) NOT NULL CHECK (montant > 0),
    sens        TEXT NOT NULL CHECK (sens IN ('apport','retrait')),
    devise      TEXT NOT NULL DEFAULT 'EUR',
    taux_eur    NUMERIC(20,10) NOT NULL DEFAULT 1 CHECK (taux_eur > 0),
    montant_eur NUMERIC(18,4) GENERATED ALWAYS AS (montant * taux_eur) STORED,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_flux_support_date ON flux(support_id, date DESC);


-- ── 5. societes ─────────────────────────────────────────────
-- Les sociétés suivies. « La note est aussi importante que le chiffre » :
-- these et notes sont du markdown libre, éditable, jamais généré.
-- Indépendante de positions — on peut suivre une société sans la détenir.

CREATE TABLE IF NOT EXISTS societes (
    ticker      TEXT PRIMARY KEY,
    nom         TEXT,
    these       TEXT,                   -- markdown : pourquoi je la suis
    notes       TEXT,                   -- markdown : journal libre
    statut      TEXT NOT NULL DEFAULT 'suivie'
                CHECK (statut IN ('suivie','detenue','sortie','archivee')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_societes_statut ON societes(statut);

DROP TRIGGER IF EXISTS tr_societes_touch ON societes;
CREATE TRIGGER tr_societes_touch BEFORE UPDATE ON societes
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- ── 6. RLS ──────────────────────────────────────────────────
-- Ces tables sont écrites depuis le navigateur (écran de saisie), avec la
-- clé anon + session utilisateur → rôle `authenticated`. Contrairement à
-- ticker_scores (écrite par le daemon en service_role), elles ont donc
-- besoin de policies d'écriture pour `authenticated`.
-- Aucune policy pour `anon` : non authentifié = rien.

ALTER TABLE supports  ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE flux      ENABLE ROW LEVEL SECURITY;
ALTER TABLE societes  ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['supports','positions','snapshots','flux','societes']
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', 'authenticated all ' || t, t);
        EXECUTE format(
            'CREATE POLICY %I ON %I FOR ALL TO authenticated USING (true) WITH CHECK (true)',
            'authenticated all ' || t, t);
    END LOOP;
END $$;


-- ── 7. Amorçage des 4 supports ──────────────────────────────
-- Les montants ne sont jamais dans le repo — seuls les contenants le sont.

INSERT INTO supports (nom, type, devise, classe_dominante, ordre) VALUES
    ('Bitpanda',       'exchange',    'EUR', 'crypto',  1),
    ('Revolut',        'broker',      'EUR', NULL,      2),  -- mixte : classe indéterminée
    ('Trade Republic', 'broker',      'EUR', 'actions', 3),
    ('Ledger',         'cold_wallet', 'EUR', 'crypto',  4)
ON CONFLICT (nom) DO NOTHING;


-- ============================================================
-- 8. portfolio_holdings — NON MIGRÉE, NON SUPPRIMÉE
-- ============================================================
-- Colonnes constatées via le code du frontend : id, user_id, ticker,
-- quantity, buy_price, added_at. Actions uniquement, aucune notion de
-- support : impossible de déduire automatiquement vers quel support
-- rattacher chaque ligne. La table est donc laissée intacte.
--
-- Inspecter avant de décider :
--
--   SELECT ticker, quantity, buy_price, added_at
--     FROM portfolio_holdings
--    ORDER BY added_at DESC;
--
-- Reprise manuelle, une fois le support choisi (exemple Trade Republic) :
--
--   INSERT INTO positions (support_id, actif, classe, notes)
--   SELECT (SELECT id FROM supports WHERE nom = 'Trade Republic'),
--          h.ticker, 'actions',
--          'Repris de portfolio_holdings — PRU saisi ' || h.buy_price
--     FROM portfolio_holdings h
--   ON CONFLICT (support_id, actif) DO NOTHING;
--
-- Puis DROP TABLE portfolio_holdings; une fois la reprise vérifiée.
-- Les quantités ne sont volontairement pas reprises : le modèle veut un
-- snapshot daté, pas une quantité flottante sans date de constat.
