-- ============================================================
-- Base miroir — preuve fonctionnelle du partage par rôle
-- ============================================================
-- Rejoue une lecture ET une écriture sur ticker_scores et sur supports,
-- sous chacun des trois rôles Supabase, policies du pivot appliquées.
-- Ce que la miroir dit ici, la prod le dira.
-- ============================================================

\set ON_ERROR_STOP on

-- Le propriétaire des tables contourne RLS par défaut : sans ça, SET ROLE
-- ne prouverait rien.
ALTER TABLE ticker_scores FORCE ROW LEVEL SECURITY;
ALTER TABLE score_history FORCE ROW LEVEL SECURITY;
ALTER TABLE supports      FORCE ROW LEVEL SECURITY;
ALTER TABLE snapshots     FORCE ROW LEVEL SECURITY;

DO $$
DECLARE
    n INT;
    msg TEXT;
BEGIN
    -- Jeu d'essai posé en tant que propriétaire.
    INSERT INTO ticker_scores (ticker, score_total) VALUES ('ZZTEST', 42)
    ON CONFLICT (ticker) DO UPDATE SET score_total = 42;

    -- ── service_role : le daemon ────────────────────────────
    SET LOCAL ROLE service_role;
    SELECT count(*) INTO n FROM ticker_scores WHERE ticker = 'ZZTEST';
    IF n <> 1 THEN RAISE EXCEPTION 'ECHEC : service_role ne peut pas LIRE ticker_scores'; END IF;
    RAISE NOTICE 'OK  service_role  LIT   ticker_scores';

    UPDATE ticker_scores SET score_total = 43 WHERE ticker = 'ZZTEST';
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN RAISE EXCEPTION 'ECHEC : service_role ne peut pas ECRIRE ticker_scores'; END IF;
    RAISE NOTICE 'OK  service_role  ECRIT ticker_scores  <- le daemon continue de tourner';
    RESET ROLE;

    -- ── authenticated : le navigateur ───────────────────────
    SET LOCAL ROLE authenticated;
    SELECT count(*) INTO n FROM ticker_scores WHERE ticker = 'ZZTEST';
    IF n <> 1 THEN RAISE EXCEPTION 'ECHEC : authenticated ne peut pas LIRE ticker_scores'; END IF;
    RAISE NOTICE 'OK  authenticated LIT   ticker_scores';

    BEGIN
        UPDATE ticker_scores SET score_total = 99 WHERE ticker = 'ZZTEST';
        GET DIAGNOSTICS n = ROW_COUNT;
        IF n > 0 THEN
            RAISE EXCEPTION 'ECHEC : authenticated a ECRIT dans ticker_scores (donnee machine)';
        END IF;
        RAISE NOTICE 'OK  authenticated N''ECRIT PAS ticker_scores (0 ligne touchee)';
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK  authenticated N''ECRIT PAS ticker_scores (refus explicite)';
    END;

    -- Tables patrimoniales : lecture ET écriture
    INSERT INTO supports (nom, type, devise, classe_dominante)
    VALUES ('__role_test__', 'broker', 'EUR', 'actions');
    RAISE NOTICE 'OK  authenticated ECRIT supports        <- l''ecran de saisie fonctionne';

    INSERT INTO snapshots (niveau, support_id, date, valeur)
    VALUES ('support', (SELECT id FROM supports WHERE nom='__role_test__'), CURRENT_DATE, 1);
    RAISE NOTICE 'OK  authenticated ECRIT snapshots       <- la saisie hebdo fonctionne';

    SELECT count(*) INTO n FROM supports WHERE nom = '__role_test__';
    IF n <> 1 THEN RAISE EXCEPTION 'ECHEC : authenticated ne relit pas ce qu''il vient d''ecrire'; END IF;
    RAISE NOTICE 'OK  authenticated LIT   supports';
    RESET ROLE;

    -- ── anon : le visiteur non authentifié ──────────────────
    SET LOCAL ROLE anon;
    SELECT count(*) INTO n FROM ticker_scores WHERE ticker = 'ZZTEST';
    IF n <> 0 THEN RAISE EXCEPTION 'ECHEC : anon LIT ticker_scores — la fermeture n''a pas pris'; END IF;
    RAISE NOTICE 'OK  anon          NE LIT PAS ticker_scores';

    -- Deux issues acceptables, et la seconde est la plus forte :
    --   0 ligne             -> RLS a filtré
    --   permission denied   -> le GRANT a refusé avant même RLS
    BEGIN
        SELECT count(*) INTO n FROM supports;
        IF n <> 0 THEN RAISE EXCEPTION 'ECHEC : anon LIT supports — le patrimoine est expose'; END IF;
        RAISE NOTICE 'OK  anon          NE LIT PAS supports    (RLS filtre, 0 ligne)';
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK  anon          NE LIT PAS supports    (refus de privilege, avant RLS)';
    END;

    BEGIN
        INSERT INTO ticker_scores (ticker, score_total) VALUES ('ZZANON', 1);
        RAISE EXCEPTION 'ECHEC : anon a ECRIT dans ticker_scores';
    EXCEPTION
        WHEN insufficient_privilege THEN RAISE NOTICE 'OK  anon          N''ECRIT PAS ticker_scores';
        WHEN check_violation THEN RAISE NOTICE 'OK  anon          N''ECRIT PAS ticker_scores';
    END;
    RESET ROLE;

    -- Nettoyage
    DELETE FROM snapshots WHERE support_id IN (SELECT id FROM supports WHERE nom='__role_test__');
    DELETE FROM supports  WHERE nom = '__role_test__';
    DELETE FROM ticker_scores WHERE ticker IN ('ZZTEST','ZZANON');

    RAISE NOTICE '---';
    RAISE NOTICE 'PARTAGE PAR ROLE CONFORME';
END $$;

ALTER TABLE ticker_scores NO FORCE ROW LEVEL SECURITY;
ALTER TABLE score_history NO FORCE ROW LEVEL SECURITY;
ALTER TABLE supports      NO FORCE ROW LEVEL SECURITY;
ALTER TABLE snapshots     NO FORCE ROW LEVEL SECURITY;
