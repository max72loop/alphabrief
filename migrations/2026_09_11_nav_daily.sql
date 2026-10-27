-- Photo quotidienne de la valeur du compte (Max, 2026-09-11 : « j'aimerais les
-- deux » — l'évolution PRIX à composition constante existe déjà, celle-ci est
-- l'évolution du COMPTE, apports et arbitrages compris).
--
-- Une ligne par jour, écrite par pixel-office-api (cron 23:00 Europe/Paris,
-- après la clôture US) à partir du total live de /api/patrimoine. Idempotente :
-- rejouer le même jour écrase la photo, on garde la dernière.
CREATE TABLE IF NOT EXISTS nav_daily (
  date        date PRIMARY KEY,
  total_eur   numeric(14,2) NOT NULL,
  estime_eur  numeric(14,2) NOT NULL DEFAULT 0,   -- part non cotée (cash) entrée à la saisie
  complet     boolean NOT NULL DEFAULT true,       -- false si une poche est estimée
  source      text NOT NULL DEFAULT 'pixel_office',
  created_at  timestamptz NOT NULL DEFAULT now()
);
