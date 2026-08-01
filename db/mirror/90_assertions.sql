-- ============================================================
-- Base miroir — assertions sémantiques
-- ============================================================
-- Une migration qui tourne sans erreur n'est pas une migration correcte.
-- Ce fichier vérifie la SÉMANTIQUE. Toute assertion fausse lève une
-- exception et fait échouer `make db-reset` avec un code non nul.
--
-- Les assertions 1, 2a, 2b, 2c et 3 de la version Supabase ont été retirées
-- le 2026-08-01 : elles vérifiaient des policies RLS, des privilèges de rôles
-- (`anon`, `authenticated`, `service_role`) et l'absence de la table `alerts`.
-- Aucun de ces objets n'existe plus. Ce qui reste — le non-double-comptage,
-- le XOR des snapshots, la colonne générée — ne dépendait pas de Supabase et
-- reste vrai mot pour mot.
-- ============================================================

\set ON_ERROR_STOP on

DO $$
DECLARE
    n INT;
    v NUMERIC;
    t TEXT;
BEGIN
    -- ── 1. XOR des snapshots réellement appliqué ────────────
    INSERT INTO supports (nom, type, devise, classe_dominante)
    VALUES ('__test__', 'broker', 'EUR', 'actions')
    ON CONFLICT (nom) DO NOTHING;

    BEGIN
        INSERT INTO snapshots (niveau, support_id, position_id, date, valeur)
        VALUES ('support', (SELECT id FROM supports WHERE nom='__test__'), 1, CURRENT_DATE, 100);
        RAISE EXCEPTION 'ECHEC 1 : un snapshot avec les DEUX FK a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 1a support_id + position_id ensemble : rejete';
    END;

    BEGIN
        INSERT INTO snapshots (niveau, date, valeur) VALUES ('support', CURRENT_DATE, 100);
        RAISE EXCEPTION 'ECHEC 1 : un snapshot sans aucune FK a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 1b aucune FK : rejete';
    END;

    BEGIN
        INSERT INTO snapshots (niveau, support_id, date, valeur)
        VALUES ('position', (SELECT id FROM supports WHERE nom='__test__'), CURRENT_DATE, 100);
        RAISE EXCEPTION 'ECHEC 1 : niveau=position avec un support_id a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 1c niveau et FK ne peuvent pas diverger';
    END;

    -- ── 2. Unicité (support_id, date, niveau) ───────────────
    INSERT INTO snapshots (niveau, support_id, date, valeur)
    VALUES ('support', (SELECT id FROM supports WHERE nom='__test__'), '2026-01-01', 1000);
    BEGIN
        INSERT INTO snapshots (niveau, support_id, date, valeur)
        VALUES ('support', (SELECT id FROM supports WHERE nom='__test__'), '2026-01-01', 2000);
        RAISE EXCEPTION 'ECHEC 2 : doublon (support, date, niveau) accepte';
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'OK 2  un seul snapshot par support et par date';
    END;

    -- ── 3. valeur_eur est bien dérivée, non saisissable ─────
    UPDATE snapshots SET valeur = 500, taux_eur = 1.2
     WHERE support_id = (SELECT id FROM supports WHERE nom='__test__');
    SELECT valeur_eur INTO v FROM snapshots
     WHERE support_id = (SELECT id FROM supports WHERE nom='__test__');
    IF v <> 600 THEN
        RAISE EXCEPTION 'ECHEC 3 : valeur_eur = % au lieu de 600', v;
    END IF;
    RAISE NOTICE 'OK 3  valeur_eur derivee (500 x 1.2 = 600)';

    -- ── 4. classe_dominante NOT NULL ────────────────────────
    BEGIN
        INSERT INTO supports (nom, type, devise, classe_dominante)
        VALUES ('__test_null__', 'broker', 'EUR', NULL);
        RAISE EXCEPTION 'ECHEC 4 : un support sans classe a ete accepte';
    EXCEPTION WHEN not_null_violation THEN
        RAISE NOTICE 'OK 4  classe_dominante obligatoire, pas d''indetermine';
    END;

    -- ── 5. LE POINT CLÉ : v_patrimoine_total ignore les positions ─
    INSERT INTO positions (support_id, actif, classe)
    VALUES ((SELECT id FROM supports WHERE nom='__test__'), 'TEST', 'actions')
    ON CONFLICT DO NOTHING;

    INSERT INTO snapshots (niveau, position_id, date, valeur)
    VALUES ('position', (SELECT id FROM positions WHERE actif='TEST'), '2026-01-01', 999999);

    SELECT total_eur INTO v FROM v_patrimoine_total WHERE date = '2026-01-01';
    IF v <> 600 THEN
        RAISE EXCEPTION 'ECHEC 5 : DOUBLE COMPTAGE — total = % au lieu de 600', v;
    END IF;
    RAISE NOTICE 'OK 5  total = 600 malgre un snapshot position de 999999 : pas de double comptage';

    -- ── 6. La réconciliation voit l'écart sans le compter ───
    SELECT ecart_eur INTO v FROM v_reconciliation_positions WHERE date = '2026-01-01';
    IF v <> 600 - 999999 THEN
        RAISE EXCEPTION 'ECHEC 6 : ecart de reconciliation = % au lieu de %', v, 600-999999;
    END IF;
    RAISE NOTICE 'OK 6  ecart expose comme information (%), jamais additionne', v;

    -- ── 7. anciennete_jours alimente l'indicateur > 10 j ───
    SELECT anciennete_jours INTO n FROM v_support_dernier_snapshot
     WHERE nom = '__test__';
    IF n IS NULL OR n < 1 THEN
        RAISE EXCEPTION 'ECHEC 7 : anciennete_jours vaut %', n;
    END IF;
    RAISE NOTICE 'OK 7  anciennete_jours calculee (% jours)', n;

    -- ── Nettoyage ──────────────────────────────────────────
    DELETE FROM snapshots WHERE support_id IN (SELECT id FROM supports WHERE nom='__test__')
                             OR position_id IN (SELECT id FROM positions WHERE actif='TEST');
    DELETE FROM positions WHERE actif = 'TEST';
    DELETE FROM supports  WHERE nom LIKE '\_\_test%';

    RAISE NOTICE '---';
    RAISE NOTICE 'TOUTES LES ASSERTIONS PASSENT';
END $$;
