-- ============================================================
-- Base miroir — policies du point de départ
-- ============================================================
-- La STRUCTURE ne vient plus d'ici : elle est chargée depuis
-- db/schema.reference.sql, introspecté sur la vraie base. Ce fichier ne
-- pose plus que les POLICIES dangereuses d'avant migration, que
-- l'introspection PostgREST ne peut pas voir.
--
-- `alerts` est absente du dump réel : c'est reproduit de fait, sans qu'on
-- ait à y penser. C'était précisément la fragilité de l'ancien fichier
-- écrit à la main.
-- ============================================================

ALTER TABLE ticker_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read ticker_scores"  ON ticker_scores;
DROP POLICY IF EXISTS "Public read score_history"  ON score_history;
DROP POLICY IF EXISTS "Service write ticker_scores" ON ticker_scores;
DROP POLICY IF EXISTS "Service write score_history" ON score_history;

CREATE POLICY "Public read ticker_scores" ON ticker_scores
    FOR SELECT USING (true);
CREATE POLICY "Public read score_history" ON score_history
    FOR SELECT USING (true);

-- LE TROU : FOR ALL sans clause TO → s'applique à `public`, donc à `anon`.
CREATE POLICY "Service write ticker_scores" ON ticker_scores
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service write score_history" ON score_history
    FOR ALL USING (true) WITH CHECK (true);

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['paper_portfolios','paper_positions','paper_rebalances',
                             'paper_nav_history','paper_metrics','paper_missed_rebalances',
                             'paper_corporate_actions','paper_sofr_rates']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', 'Public read ' || t, t);
        EXECUTE format('CREATE POLICY %I ON %I FOR SELECT USING (true)',
                       'Public read ' || t, t);
    END LOOP;
END $$;
