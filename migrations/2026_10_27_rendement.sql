-- ============================================================
-- AlphaBrief — Prime de rendement et photo quotidienne des poches
-- Appliquée par `make db-apply` APRÈS la classe « or ».
-- ============================================================
--
-- 1. `ticker_scores.rendement` (JSONB) : le bloc `rendement` de la carte
--    (core/scoring/prime.py — taux 10 ans, earnings yield, FCF yield, prime,
--    flag vert/orange/rouge/na) et la dilution par an sur 1 et 3 ans
--    (core/scoring/dilution.py), lus par la fiche Ticker du cockpit. NULL tant
--    qu'aucun scoring ne l'a écrit : `writer.write_score` ne l'inclut que si la
--    colonne existe, la prod tourne donc avant comme après cette migration.
--    La prime est EN OMBRE (décision du 2026-10-27) : affichée, jamais dans la note.
--
-- 2. `poche_daily` : valeur de chaque classe d'actif, une photo par jour (prise
--    avec `nav_daily` par l'API Pixel Office). `nav_daily` ne porte que le total,
--    apports compris : impossible d'en tirer le TWR de la poche actions, qui est
--    la mesure de l'objectif de Sage (battre le MSCI World de +3,5 pts/an). Le
--    TWR se calcule ensuite avec `flux` (apports/retraits par support).
--    `estime_eur` = part non cotée retombée sur la dernière saisie, comme
--    `nav_daily.estime_eur`.
--
-- Idempotente : rejouable sans effet de bord (vérifié par `make db-reset`).
-- Ne supprime rien.
-- ============================================================

ALTER TABLE ticker_scores ADD COLUMN IF NOT EXISTS rendement JSONB;

CREATE TABLE IF NOT EXISTS poche_daily (
    date        DATE NOT NULL,
    classe      TEXT NOT NULL CHECK (classe IN ('actions','crypto','cash','or')),
    valeur_eur  NUMERIC(14,2) NOT NULL,
    estime_eur  NUMERIC(14,2) NOT NULL DEFAULT 0,
    source      TEXT NOT NULL DEFAULT 'pixel_office',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, classe)
);
