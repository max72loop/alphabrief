-- ============================================================
-- Base miroir — contraintes que l'introspection ne voit pas
-- ============================================================
-- CE QUE db/schema.reference.sql CAPTURE, via la spec OpenAPI PostgREST :
--   colonnes, types, valeurs par défaut, nullabilité, clé primaire.
--
-- CE QU'IL NE CAPTURE PAS :
--   contraintes UNIQUE (hors PK), cibles exactes des clés étrangères,
--   contraintes CHECK, index, triggers.
--
-- Ces éléments sont donc déclarés ici À LA MAIN, ce qui les expose à la
-- même dérive que l'ancien supabase_schema.sql. La parade : n'y mettre que
-- ce dont on a la PREUVE en prod, et écrire cette preuve à côté.
--
-- ⚠ `make db-drift` ne surveille PAS ce fichier — il ne compare que ce que
--   l'introspection sait lire. C'est la limite connue du dispositif.
-- ============================================================

-- ticker_scores.ticker est UNIQUE.
-- Preuve : le daemon fait `.upsert(row, on_conflict="ticker")` sur la prod
-- et reçoit HTTP 200 (vérifié le 2026-07-31). Un ON CONFLICT sans contrainte
-- unique correspondante échouerait en « there is no unique or exclusion
-- constraint matching the ON CONFLICT specification » — ce qui est
-- exactement l'erreur qu'a levée la miroir tant qu'elle l'ignorait.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.ticker_scores'::regclass
           AND contype = 'u'
    ) THEN
        ALTER TABLE ticker_scores ADD CONSTRAINT ticker_scores_ticker_key UNIQUE (ticker);
    END IF;
END $$;

-- Les triggers append-only des tables paper_* ne sont pas reproduits : ils
-- sont orthogonaux à RLS et aucune migration du pivot ne les touche.
