-- ============================================================
-- Base miroir — assertions
-- ============================================================
-- Une migration qui tourne sans erreur n'est pas une migration correcte.
-- Ce fichier vérifie la SÉMANTIQUE. Toute assertion fausse lève une
-- exception et fait échouer `make db-reset` avec un code non nul.
-- ============================================================

\set ON_ERROR_STOP on

DO $$
DECLARE
    n INT;
    v NUMERIC;
    ok BOOLEAN;
BEGIN
    -- ── 1. Plus aucune policy ouverte à public/anon ─────────
    SELECT count(*) INTO n
      FROM pg_policies
     WHERE schemaname = 'public'
       AND (roles::text[] && ARRAY['public','anon']);
    IF n <> 0 THEN
        RAISE EXCEPTION 'ECHEC 1 : % policy(ies) encore ouverte(s) a public/anon', n;
    END IF;
    RAISE NOTICE 'OK 1  aucune policy ouverte a public ou anon';

    -- ── 2. Aucune écriture possible sur les tables de scoring ─
    SELECT count(*) INTO n
      FROM pg_policies
     WHERE schemaname = 'public'
       AND tablename IN ('ticker_scores','score_history')
       AND cmd <> 'SELECT';
    IF n <> 0 THEN
        RAISE EXCEPTION 'ECHEC 2 : % policy(ies) d''ecriture subsistent sur les tables de scoring', n;
    END IF;
    RAISE NOTICE 'OK 2  ecriture reservee a service_role (aucune policy non-SELECT)';

    -- ── 3. La migration a survécu à l'absence de `alerts` ────
    IF to_regclass('public.alerts') IS NOT NULL THEN
        RAISE EXCEPTION 'ECHEC 3 : alerts ne devrait pas exister dans l''etat miroir';
    END IF;
    SELECT count(*) INTO n FROM pg_policies
     WHERE schemaname='public' AND tablename='ticker_scores' AND cmd='SELECT';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ECHEC 3 : la migration ne s''est pas appliquee apres avoir saute alerts';
    END IF;
    RAISE NOTICE 'OK 3  table absente ignoree, la migration continue';

    -- ── 4. XOR des snapshots réellement appliqué ────────────
    INSERT INTO supports (nom, type, devise, classe_dominante)
    VALUES ('__test__', 'broker', 'EUR', 'actions')
    ON CONFLICT (nom) DO NOTHING;

    BEGIN
        INSERT INTO snapshots (niveau, support_id, position_id, date, valeur)
        VALUES ('support', (SELECT id FROM supports WHERE nom='__test__'), 1, CURRENT_DATE, 100);
        RAISE EXCEPTION 'ECHEC 4 : un snapshot avec les DEUX FK a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 4a support_id + position_id ensemble : rejete';
    END;

    BEGIN
        INSERT INTO snapshots (niveau, date, valeur) VALUES ('support', CURRENT_DATE, 100);
        RAISE EXCEPTION 'ECHEC 4 : un snapshot sans aucune FK a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 4b aucune FK : rejete';
    END;

    BEGIN
        INSERT INTO snapshots (niveau, support_id, date, valeur)
        VALUES ('position', (SELECT id FROM supports WHERE nom='__test__'), CURRENT_DATE, 100);
        RAISE EXCEPTION 'ECHEC 4 : niveau=position avec un support_id a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 4c niveau et FK ne peuvent pas diverger';
    END;

    -- ── 5. Unicité (support_id, date, niveau) ───────────────
    INSERT INTO snapshots (niveau, support_id, date, valeur)
    VALUES ('support', (SELECT id FROM supports WHERE nom='__test__'), '2026-01-01', 1000);
    BEGIN
        INSERT INTO snapshots (niveau, support_id, date, valeur)
        VALUES ('support', (SELECT id FROM supports WHERE nom='__test__'), '2026-01-01', 2000);
        RAISE EXCEPTION 'ECHEC 5 : doublon (support, date, niveau) accepte';
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'OK 5  un seul snapshot par support et par date';
    END;

    -- ── 6. valeur_eur est bien dérivée, non saisissable ─────
    UPDATE snapshots SET valeur = 500, taux_eur = 1.2
     WHERE support_id = (SELECT id FROM supports WHERE nom='__test__');
    SELECT valeur_eur INTO v FROM snapshots
     WHERE support_id = (SELECT id FROM supports WHERE nom='__test__');
    IF v <> 600 THEN
        RAISE EXCEPTION 'ECHEC 6 : valeur_eur = % au lieu de 600', v;
    END IF;
    RAISE NOTICE 'OK 6  valeur_eur derivee (500 x 1.2 = 600)';

    -- ── 7. classe_dominante NOT NULL ────────────────────────
    BEGIN
        INSERT INTO supports (nom, type, devise, classe_dominante)
        VALUES ('__test_null__', 'broker', 'EUR', NULL);
        RAISE EXCEPTION 'ECHEC 7 : un support sans classe a ete accepte';
    EXCEPTION WHEN not_null_violation THEN
        RAISE NOTICE 'OK 7  classe_dominante obligatoire, pas d''indetermine';
    END;

    -- ── 8. LE POINT CLÉ : v_patrimoine_total ignore les positions ─
    INSERT INTO positions (support_id, actif, classe)
    VALUES ((SELECT id FROM supports WHERE nom='__test__'), 'TEST', 'actions')
    ON CONFLICT DO NOTHING;

    INSERT INTO snapshots (niveau, position_id, date, valeur)
    VALUES ('position', (SELECT id FROM positions WHERE actif='TEST'), '2026-01-01', 999999);

    SELECT total_eur INTO v FROM v_patrimoine_total WHERE date = '2026-01-01';
    IF v <> 600 THEN
        RAISE EXCEPTION 'ECHEC 8 : DOUBLE COMPTAGE — total = % au lieu de 600', v;
    END IF;
    RAISE NOTICE 'OK 8  total = 600 malgre un snapshot position de 999999 : pas de double comptage';

    -- ── 9. La réconciliation voit l'écart sans le compter ───
    SELECT ecart_eur INTO v FROM v_reconciliation_positions WHERE date = '2026-01-01';
    IF v <> 600 - 999999 THEN
        RAISE EXCEPTION 'ECHEC 9 : ecart de reconciliation = % au lieu de %', v, 600-999999;
    END IF;
    RAISE NOTICE 'OK 9  ecart expose comme information (%), jamais additionne', v;

    -- ── 10. anciennete_jours alimente l'indicateur > 10 j ───
    SELECT anciennete_jours INTO n FROM v_support_dernier_snapshot
     WHERE nom = '__test__';
    IF n IS NULL OR n < 1 THEN
        RAISE EXCEPTION 'ECHEC 10 : anciennete_jours vaut %', n;
    END IF;
    RAISE NOTICE 'OK 10 anciennete_jours calculee (% jours)', n;

    -- ── Nettoyage ──────────────────────────────────────────
    DELETE FROM snapshots WHERE support_id IN (SELECT id FROM supports WHERE nom='__test__')
                             OR position_id IN (SELECT id FROM positions WHERE actif='TEST');
    DELETE FROM positions WHERE actif = 'TEST';
    DELETE FROM supports  WHERE nom LIKE '\_\_test%';

    RAISE NOTICE '---';
    RAISE NOTICE 'TOUTES LES ASSERTIONS PASSENT';
END $$;
