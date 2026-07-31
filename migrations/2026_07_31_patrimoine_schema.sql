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
-- UN SUPPORT N'EST PAS UN COMPTE, C'EST UNE POCHE HOMOGÈNE.
--
-- Conséquence directe : un compte réellement mixte se déclare en plusieurs
-- supports. Revolut devient « Revolut Actions » et « Revolut Crypto » — deux
-- montants à saisir au lieu d'un, contre un écran de répartition sans trou.
--
-- C'est ce qui permet à `classe_dominante` d'être NOT NULL : il n'existe pas
-- de catégorie « indéterminé » dans ce schéma. Toute valeur saisie tombe
-- dans exactement une classe.

CREATE TABLE IF NOT EXISTS supports (
    id               BIGSERIAL PRIMARY KEY,
    nom              TEXT NOT NULL UNIQUE,
    type             TEXT NOT NULL
                     CHECK (type IN ('exchange','broker','cold_wallet')),
    devise           TEXT NOT NULL DEFAULT 'EUR',
    classe_dominante TEXT NOT NULL
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
-- RÈGLE DE NON-DOUBLE-COMPTAGE — MÉCANIQUE, PAS CONVENTIONNELLE.
--   La colonne `niveau` rend la distinction explicite et interrogeable au
--   lieu de la laisser déduire d'un NULL. Elle est cohérente avec les FK par
--   contrainte, pas par discipline : on ne peut pas écrire un snapshot de
--   niveau 'support' portant un position_id.
--   Le total d'un support à une date est le snapshot de niveau 'support'.
--   Le détail par position ne s'y additionne JAMAIS : il se RÉCONCILIE
--   contre lui (cf. v_reconciliation_positions, §6).
--
-- valeur_eur est dérivée, jamais saisie : c'est la contrainte « devise de
-- référence EUR, conversion au taux du jour » rendue non contournable.

CREATE TABLE IF NOT EXISTS snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    niveau              TEXT NOT NULL CHECK (niveau IN ('support','position')),
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

    -- `niveau` et les FK ne peuvent pas diverger.
    CONSTRAINT snapshot_niveau_coherent CHECK (
        (niveau = 'support'  AND support_id  IS NOT NULL AND position_id IS NULL)
     OR (niveau = 'position' AND position_id IS NOT NULL AND support_id  IS NULL)
    )
);

-- Unicité demandée : (support_id, date, niveau). Au niveau position le
-- support_id est NULL, donc la clé utile y est (position_id, date, niveau).
-- L'écran de saisie fait un upsert dessus : corriger une valeur ne crée pas
-- de doublon.
CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_support_date_niveau
    ON snapshots(support_id, date, niveau)  WHERE niveau = 'support';
CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_position_date_niveau
    ON snapshots(position_id, date, niveau) WHERE niveau = 'position';

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


-- ── 6. Vues — LE SEUL CHEMIN AUTORISÉ POUR UN TOTAL ─────────
--
-- Aucune agrégation ad hoc dans le code applicatif. Toute somme de valeurs
-- passe par v_patrimoine_total. C'est ce qui empêche un futur écran de
-- réinventer un SUM(valeur_eur) qui additionnerait support et positions.

-- Dernier snapshot de niveau support connu pour chaque support.
CREATE OR REPLACE VIEW v_support_dernier_snapshot AS
SELECT DISTINCT ON (s.id)
       s.id                AS support_id,
       s.nom,
       s.type,
       s.devise,
       s.classe_dominante,
       s.actif,
       s.ordre,
       sn.date             AS derniere_date,
       sn.valeur_eur       AS derniere_valeur_eur,
       sn.is_opening_position,
       (CURRENT_DATE - sn.date) AS anciennete_jours
  FROM supports s
  LEFT JOIN snapshots sn
         ON sn.support_id = s.id
        AND sn.niveau = 'support'
 ORDER BY s.id, sn.date DESC;

-- Total patrimonial par date : SOMME DES SNAPSHOTS DE NIVEAU SUPPORT
-- UNIQUEMENT. Le niveau 'position' est structurellement exclu.
CREATE OR REPLACE VIEW v_patrimoine_total AS
SELECT sn.date,
       SUM(sn.valeur_eur)                             AS total_eur,
       COUNT(*)                                       AS supports_renseignes,
       (SELECT COUNT(*) FROM supports WHERE actif)    AS supports_actifs
  FROM snapshots sn
 WHERE sn.niveau = 'support'
 GROUP BY sn.date;

-- Répartition par classe d'actif. Possible sans ventilation par snapshot
-- précisément parce qu'un support est une poche homogène (classe_dominante
-- NOT NULL) — c'est la contrepartie du split Revolut.
CREATE OR REPLACE VIEW v_repartition_classe AS
SELECT sn.date,
       s.classe_dominante  AS classe,
       SUM(sn.valeur_eur)  AS valeur_eur
  FROM snapshots sn
  JOIN supports s ON s.id = sn.support_id
 WHERE sn.niveau = 'support'
 GROUP BY sn.date, s.classe_dominante;

-- Réconciliation : le détail par position CONTRE le total du support, jamais
-- en plus. L'écart est une information, pas une erreur — il est normal quand
-- le détail est partiel ou plus ancien que le total.
CREATE OR REPLACE VIEW v_reconciliation_positions AS
SELECT sup.date,
       sup.support_id,
       sup.total_support_eur,
       det.total_positions_eur,
       det.positions_couvertes,
       (sup.total_support_eur - COALESCE(det.total_positions_eur, 0)) AS ecart_eur
  FROM (
        SELECT support_id, date, SUM(valeur_eur) AS total_support_eur
          FROM snapshots WHERE niveau = 'support'
         GROUP BY support_id, date
       ) sup
  LEFT JOIN (
        SELECT p.support_id, sn.date,
               SUM(sn.valeur_eur) AS total_positions_eur,
               COUNT(*)           AS positions_couvertes
          FROM snapshots sn
          JOIN positions p ON p.id = sn.position_id
         WHERE sn.niveau = 'position'
         GROUP BY p.support_id, sn.date
       ) det
    ON det.support_id = sup.support_id AND det.date = sup.date;


-- ── 7. RLS ──────────────────────────────────────────────────
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


-- ── 8. Amorçage des supports ────────────────────────────────
-- 5 supports pour 4 comptes : Revolut est scindé, un support = une poche
-- homogène. Les montants ne sont jamais dans le repo, seuls les contenants.

INSERT INTO supports (nom, type, devise, classe_dominante, ordre) VALUES
    ('Bitpanda',        'exchange',    'EUR', 'crypto',  1),
    ('Trade Republic',  'broker',      'EUR', 'actions', 2),
    ('Revolut Actions', 'broker',      'EUR', 'actions', 3),
    ('Revolut Crypto',  'broker',      'EUR', 'crypto',  4),
    ('Ledger',          'cold_wallet', 'EUR', 'crypto',  5)
ON CONFLICT (nom) DO NOTHING;


-- ============================================================
-- 9. portfolio_holdings — SANS OBJET, LA TABLE N'EXISTE PAS
-- ============================================================
-- Vérifié le 2026-07-31 contre le projet Supabase réel : PostgREST renvoie
-- PGRST205, « Could not find the table 'public.portfolio_holdings' in the
-- schema cache ». Elle n'a jamais été créée.
--
-- Le frontend l'interrogeait donc dans le vide : /portfolio et
-- /api/portfolio échouaient en silence (le select renvoyait une erreur,
-- `holdings` restait undefined, la page affichait une liste vide).
--
-- Rien à dumper, rien à archiver, rien à supprimer. La demande « dump CSV
-- puis DROP TABLE » est sans objet.
--
-- Reste à traiter au lot 2 : /portfolio et /api/portfolio sont du code mort
-- pointant vers une table inexistante. Ils sont remplacés par l'écran de
-- saisie, pas conservés.
--
-- ⚠ `alerts` est dans le même cas (PGRST205). Conséquences en prod :
--    - le daemon appelle write_alert() → échoue, log en WARNING, continue
--    - AppNav compte les non-lues → catch → 0
--    - le panneau d'alertes du dashboard est vide en permanence
--   La fonctionnalité d'alertes n'a jamais tourné côté Supabase. À décider
--   au lot 4 : créer la table, ou retirer la surface.
