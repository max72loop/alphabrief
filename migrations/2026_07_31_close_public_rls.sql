-- ============================================================
-- AlphaBrief — Lot 0 : fermeture des RLS publiques
-- À exécuter dans le SQL Editor du dashboard Supabase
-- ============================================================
--
-- CONTEXTE
-- Le produit devient un gestionnaire de patrimoine personnel. Les tables
-- ci-dessous vont porter des montants réels. Leurs policies actuelles,
-- héritées du screener public, sont incompatibles avec ça.
--
-- CE QUE LA MIGRATION CORRIGE
--
-- 1. Lecture publique — supabase_schema.sql et supabase_paper_portfolio_001_init.sql
--    posent `FOR SELECT USING (true)` sur 11 tables. Choix cohérent pour un
--    screener (« la preuve publique »), fuite dès que le patrimoine y entre.
--
-- 2. ÉCRITURE PUBLIQUE — plus grave. supabase_schema.sql lignes 183-191 :
--
--        CREATE POLICY "Service write ticker_scores" ON ticker_scores
--            FOR ALL USING (true) WITH CHECK (true);
--
--    Le commentaire dit « écriture via service_role key », mais la policy ne
--    restreint aucun rôle : elle s'applique à `public`, donc à `anon`. Or la
--    clé anon est publique par construction (NEXT_PUBLIC_SUPABASE_ANON_KEY est
--    servie au navigateur). Résultat : n'importe qui ayant ouvert le site peut
--    INSERT / UPDATE / DELETE sur ticker_scores, score_history et alerts.
--    Ces policies sont inutiles en plus d'être dangereuses : service_role
--    bypasse RLS par design et n'a jamais eu besoin d'une policy.
--
-- MODÈLE CIBLE
--    Lecture  : rôle `authenticated` uniquement (mono-utilisateur).
--    Écriture : aucune policy — donc réservée à service_role, qui bypasse RLS.
--    Le daemon écrit avec une clé `sb_secret_…` (vérifié), il n'est pas affecté.
--
-- ⚠ CE QUE ÇA CASSE, VOLONTAIREMENT
--    Deux pages du frontend lisent Supabase sans authentification :
--      - `/`       (landing : DailyEdition, TickerTape)
--      - `/search`
--    Elles cesseront de renvoyer des données. C'est l'effet recherché : la
--    landing est supprimée au lot 1, et /search doit passer derrière l'auth.
--    Toutes les autres pages (/marche, /compare, /historique, /watchlist,
--    /portfolio, /alerts, /settings) font déjà leur propre `getUser()` +
--    redirect — vérifié — et continuent de fonctionner pour un utilisateur
--    connecté.
--
-- ⚠ AVANT D'EXÉCUTER
--    Cette migration est écrite à partir des fichiers SQL du repo. L'état
--    réellement déployé peut avoir divergé. Lancer d'abord la requête de
--    vérification en fin de fichier (§4) et comparer.
--
-- Idempotente : rejouable sans effet de bord.
-- ============================================================


-- ── 1. Tables de scoring (supabase_schema.sql) ──────────────

ALTER TABLE ticker_scores  ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_history  ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts         ENABLE ROW LEVEL SECURITY;

-- Lecture publique
DROP POLICY IF EXISTS "Public read ticker_scores" ON ticker_scores;
DROP POLICY IF EXISTS "Public read score_history" ON score_history;
DROP POLICY IF EXISTS "Public read alerts"        ON alerts;

-- Écriture ouverte à anon (le vrai trou — cf. §2 de l'en-tête)
DROP POLICY IF EXISTS "Service write ticker_scores" ON ticker_scores;
DROP POLICY IF EXISTS "Service write score_history" ON score_history;
DROP POLICY IF EXISTS "Service write alerts"        ON alerts;

CREATE POLICY "authenticated read ticker_scores" ON ticker_scores
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated read score_history" ON score_history
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated read alerts" ON alerts
    FOR SELECT TO authenticated USING (true);


-- ── 2. Tables paper_* (bac à sable d'allocation) ────────────
-- Renommées sandbox_* au lot 1 ; on sécurise sous leur nom actuel.
-- Les triggers append-only restent en place, ils sont orthogonaux à RLS.

ALTER TABLE paper_portfolios        ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_positions         ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_rebalances        ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_nav_history       ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_metrics           ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_missed_rebalances ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_corporate_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_sofr_rates        ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read paper_portfolios"        ON paper_portfolios;
DROP POLICY IF EXISTS "Public read paper_positions"         ON paper_positions;
DROP POLICY IF EXISTS "Public read paper_rebalances"        ON paper_rebalances;
DROP POLICY IF EXISTS "Public read paper_nav_history"       ON paper_nav_history;
DROP POLICY IF EXISTS "Public read paper_metrics"           ON paper_metrics;
DROP POLICY IF EXISTS "Public read paper_missed_rebalances" ON paper_missed_rebalances;
DROP POLICY IF EXISTS "Public read paper_corporate_actions" ON paper_corporate_actions;
DROP POLICY IF EXISTS "Public read paper_sofr_rates"        ON paper_sofr_rates;

CREATE POLICY "authenticated read paper_portfolios" ON paper_portfolios
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated read paper_positions" ON paper_positions
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated read paper_rebalances" ON paper_rebalances
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated read paper_nav_history" ON paper_nav_history
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated read paper_metrics" ON paper_metrics
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated read paper_missed_rebalances" ON paper_missed_rebalances
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated read paper_corporate_actions" ON paper_corporate_actions
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "authenticated read paper_sofr_rates" ON paper_sofr_rates
    FOR SELECT TO authenticated USING (true);


-- ── 3. HORS PÉRIMÈTRE DU LOT 0 ──────────────────────────────
-- profiles, watchlists, watchlist_tickers, portfolio_holdings, ticker_events
-- sont référencées par le frontend mais n'ont AUCUN fichier de schéma dans le
-- repo — leurs policies ont été créées à la main dans le dashboard. Elles
-- portent probablement des règles par user_id qu'on casserait en aveugle.
-- Elles sont traitées au lot 1, quand le multi-tenant est aplati.
-- La requête §4 les inclut pour qu'on voie leur état avant d'y toucher.


-- ── 4. VÉRIFICATION — à lancer AVANT et APRÈS ───────────────
--
-- Attendu après migration : aucune ligne avec roles = {public} ou {anon},
-- et aucune ligne cmd = ALL / INSERT / UPDATE / DELETE sur les tables du §1-2.
--
--   SELECT tablename,
--          policyname,
--          roles,
--          cmd,
--          qual        AS using_expr,
--          with_check
--     FROM pg_policies
--    WHERE schemaname = 'public'
--    ORDER BY (roles::text[] && ARRAY['public','anon']) DESC,  -- les fuites d'abord
--             tablename,
--             cmd;
--
-- Et pour repérer une table qui porterait des données sans RLS du tout :
--
--   SELECT c.relname AS table_sans_rls
--     FROM pg_class c
--     JOIN pg_namespace n ON n.oid = c.relnamespace
--    WHERE n.nspname = 'public'
--      AND c.relkind = 'r'
--      AND NOT c.relrowsecurity
--    ORDER BY 1;


-- ── 5. DURCISSEMENT OPTIONNEL (après le lot 1) ──────────────
-- Mono-utilisateur : une fois l'uid du compte connu, on peut passer de
-- « tout utilisateur authentifié » à « ce compte précis ». Remplacer alors
-- USING (true) par :
--
--     USING (auth.uid() = '<uid>'::uuid)
--
-- Utile seulement si d'autres comptes peuvent exister sur ce projet Supabase.
-- Tant que l'inscription est fermée, `authenticated` suffit.
