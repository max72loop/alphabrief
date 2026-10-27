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

    -- ── 8. secteur_gics : GICS seulement, et jamais sans source ni date ─
    BEGIN
        INSERT INTO societes (ticker, secteur_gics, secteur_source, secteur_updated_at)
        VALUES ('__TEST__', 'Consumer Cyclical', 'yf-direct', now());
        RAISE EXCEPTION 'ECHEC 8 : un libelle fournisseur non normalise a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 8a secteur_gics refuse « Consumer Cyclical » (pas GICS)';
    END;

    BEGIN
        INSERT INTO societes (ticker, secteur_gics) VALUES ('__TEST__', 'Energy');
        RAISE EXCEPTION 'ECHEC 8 : un secteur sans source ni date a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 8b un secteur pose est source et date';
    END;

    INSERT INTO societes (ticker, secteur_gics, secteur_source, secteur_updated_at)
    VALUES ('__TEST__', 'Energy', 'yf-direct', now());

    -- ── 9. Une phase déclarée est datée, et hors des quatre rien ne passe ─
    BEGIN
        INSERT INTO cycle_phase_declarations (phase) VALUES ('boom');
        RAISE EXCEPTION 'ECHEC 9 : une phase hors modele a ete acceptee';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 9a phase hors des quatre : rejetee';
    END;

    INSERT INTO cycle_phase_declarations (phase) VALUES ('expansion');
    SELECT phase INTO t FROM cycle_phase_declarations ORDER BY declared_at DESC, id DESC LIMIT 1;
    IF t <> 'expansion' THEN
        RAISE EXCEPTION 'ECHEC 9 : derniere declaration = % au lieu de expansion', t;
    END IF;
    SELECT COUNT(*) INTO n FROM cycle_phase_declarations WHERE declared_at IS NULL;
    IF n <> 0 THEN
        RAISE EXCEPTION 'ECHEC 9 : % declaration(s) sans date', n;
    END IF;
    RAISE NOTICE 'OK 9b la derniere declaration fait foi, et elle est datee';

    -- ── 10. Résultats trimestriels : un verdict suppose un résultat publié ─
    BEGIN
        INSERT INTO resultats_trimestriels (ticker, date_publication, verdict)
        VALUES ('__TEST__', '2026-10-28', 'battu');
        RAISE EXCEPTION 'ECHEC 10 : un verdict sans BPA publie a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 10a pas de verdict sur une publication a venir';
    END;

    BEGIN
        INSERT INTO resultats_trimestriels (ticker, date_publication, bpa_publie, verdict)
        VALUES ('__TEST__', '2026-07-22', 2.85, 'excellent');
        RAISE EXCEPTION 'ECHEC 10 : un verdict hors des trois a ete accepte';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 10b verdict hors battu/conforme/rate : rejete';
    END;

    INSERT INTO resultats_trimestriels (ticker, date_publication, bpa_attendu, bpa_publie, verdict)
    VALUES ('__TEST__', '2026-07-22', 2.91, 2.85, 'conforme');
    INSERT INTO resultats_trimestriels (ticker, date_publication, bpa_attendu, bpa_publie, verdict)
    VALUES ('__TEST__', '2026-07-22', 2.91, 2.70, 'rate')
    ON CONFLICT (ticker, date_publication) DO UPDATE SET bpa_publie = EXCLUDED.bpa_publie, verdict = EXCLUDED.verdict;
    SELECT COUNT(*) INTO n FROM resultats_trimestriels WHERE ticker = '__TEST__';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ECHEC 10 : % lignes pour une meme publication', n;
    END IF;
    RAISE NOTICE 'OK 10c une publication par societe et par date (upsert)';

    -- ── 11. L'or : une classe à part entière, et rien d'inventé ─
    INSERT INTO positions (support_id, actif, classe)
    VALUES ((SELECT id FROM supports WHERE nom='__test__'), 'TESTXAU', 'or');
    RAISE NOTICE 'OK 11a une position or est acceptee';

    BEGIN
        INSERT INTO positions (support_id, actif, classe)
        VALUES ((SELECT id FROM supports WHERE nom='__test__'), 'TESTOR', 'metaux');
        RAISE EXCEPTION 'ECHEC 11 : une classe hors modele a ete acceptee';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 11b classe hors des quatre : rejetee';
    END;

    -- Un snapshot position d'or ne bouge ni le total ni la répartition.
    INSERT INTO snapshots (niveau, position_id, date, valeur)
    VALUES ('position', (SELECT id FROM positions WHERE actif='TESTXAU'), '2026-01-01', 777);
    SELECT total_eur INTO v FROM v_patrimoine_total WHERE date = '2026-01-01';
    IF v <> 600 THEN
        RAISE EXCEPTION 'ECHEC 11 : DOUBLE COMPTAGE — total = % au lieu de 600', v;
    END IF;
    SELECT COUNT(*) INTO n FROM v_repartition_classe WHERE date = '2026-01-01' AND classe = 'or';
    IF n <> 0 THEN
        RAISE EXCEPTION 'ECHEC 11 : la repartition compte un snapshot de niveau position';
    END IF;
    RAISE NOTICE 'OK 11c total = 600 et repartition inchangee malgre l''or au niveau position';

    -- ── 12. Prime de rendement et photo des poches (2026-10-27) ─
    INSERT INTO ticker_scores (ticker, score_total, score_fundamentals, score_technicals, score_momentum)
    VALUES ('__TEST__', 50, 50, 50, 50);
    SELECT COUNT(*) INTO n FROM ticker_scores WHERE ticker = '__TEST__' AND rendement IS NULL;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ECHEC 12 : une note sans rendement devrait laisser la colonne a NULL';
    END IF;
    RAISE NOTICE 'OK 12a rendement absent = NULL (la prod sans prime reste valide)';

    UPDATE ticker_scores SET rendement = '{"prime": 2.3, "flag": "vert", "dilution": {"dilution_1y": 4.1}}'::jsonb
     WHERE ticker = '__TEST__';
    SELECT COUNT(*) INTO n FROM ticker_scores
     WHERE ticker = '__TEST__' AND rendement->>'flag' = 'vert' AND (rendement->>'prime')::numeric = 2.3
       AND (rendement #>> '{dilution,dilution_1y}')::numeric = 4.1;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ECHEC 12 : rendement JSONB mal relu';
    END IF;
    RAISE NOTICE 'OK 12b rendement JSONB : flag, prime et dilution relus';

    INSERT INTO poche_daily (date, classe, valeur_eur) VALUES ('2026-10-27', 'actions', 1000);
    INSERT INTO poche_daily (date, classe, valeur_eur, estime_eur) VALUES ('2026-10-27', 'actions', 1010, 10)
    ON CONFLICT (date, classe) DO UPDATE SET valeur_eur = EXCLUDED.valeur_eur, estime_eur = EXCLUDED.estime_eur;
    SELECT COUNT(*) INTO n FROM poche_daily WHERE date = '2026-10-27' AND classe = 'actions'
       AND valeur_eur = 1010 AND estime_eur = 10 AND source = 'pixel_office';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ECHEC 12 : une photo par jour et par classe (upsert)';
    END IF;
    RAISE NOTICE 'OK 12c poche_daily : une photo par jour et par classe, estime et source relus';

    BEGIN
        INSERT INTO poche_daily (date, classe, valeur_eur) VALUES ('2026-10-27', 'obligations', 5);
        RAISE EXCEPTION 'ECHEC 12 : une classe hors modele a ete acceptee dans poche_daily';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK 12d poche_daily : classe hors des quatre rejetee';
    END;

    BEGIN
        INSERT INTO poche_daily (date, classe, valeur_eur) VALUES ('2026-10-28', 'crypto', NULL);
        RAISE EXCEPTION 'ECHEC 12 : une photo sans valeur a ete acceptee';
    EXCEPTION WHEN not_null_violation THEN
        RAISE NOTICE 'OK 12e poche_daily : valeur obligatoire';
    END;

    -- ── Nettoyage ──────────────────────────────────────────
    DELETE FROM snapshots WHERE support_id IN (SELECT id FROM supports WHERE nom='__test__')
                             OR position_id IN (SELECT id FROM positions WHERE actif IN ('TEST','TESTXAU'));
    DELETE FROM positions WHERE actif IN ('TEST','TESTXAU');
    DELETE FROM supports  WHERE nom LIKE '\_\_test%';
    DELETE FROM societes  WHERE ticker = '__TEST__';
    DELETE FROM cycle_phase_declarations;
    DELETE FROM resultats_trimestriels WHERE ticker = '__TEST__';
    DELETE FROM ticker_scores WHERE ticker = '__TEST__';
    DELETE FROM poche_daily WHERE date = '2026-10-27';

    RAISE NOTICE '---';
    RAISE NOTICE 'TOUTES LES ASSERTIONS PASSENT';
END $$;
