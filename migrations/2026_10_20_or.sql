-- ============================================================
-- AlphaBrief — Classe d'actif « or »
-- Appliquée par `make db-apply` APRÈS les catégories de Lynch.
-- ============================================================
--
-- Née de la première ligne d'or du patrimoine, le 2026-10-20. Ni `actions`
-- ni `crypto` : la ranger dans l'une des deux fausserait la répartition par
-- classe, qui est la raison d'être de `classe` NOT NULL.
--
-- Modification minimale : seuls les deux CHECK s'élargissent. Les vues
-- (v_patrimoine_total, v_repartition_classe) groupent sur la classe sans la
-- lister, elles n'ont rien à changer.
--
-- Idempotente : rejouable sans effet de bord (vérifié par `make db-reset`).
-- ============================================================

ALTER TABLE supports DROP CONSTRAINT IF EXISTS supports_classe_dominante_check;
ALTER TABLE supports ADD CONSTRAINT supports_classe_dominante_check CHECK (
    classe_dominante IN ('actions','crypto','cash','or')
);

ALTER TABLE positions DROP CONSTRAINT IF EXISTS positions_classe_check;
ALTER TABLE positions ADD CONSTRAINT positions_classe_check CHECK (
    classe IN ('actions','crypto','cash','or')
);
