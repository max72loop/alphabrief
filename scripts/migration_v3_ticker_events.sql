-- Migration v3 : ticker_events
-- Table des événements annotés sur le graphique d'historique du score
-- (earnings publiés/à venir, dividendes, splits, annonces manuelles)

CREATE TABLE IF NOT EXISTS ticker_events (
  id          bigserial PRIMARY KEY,
  ticker      text NOT NULL,
  event_date  date NOT NULL,
  label       text NOT NULL,
  kind        text NOT NULL,   -- 'earnings' | 'dividend' | 'split' | 'manual'
  source      text,            -- 'yfinance' | 'fmp' | 'manual'
  created_at  timestamptz DEFAULT now(),
  UNIQUE(ticker, event_date, kind)
);

CREATE INDEX IF NOT EXISTS idx_ticker_events_ticker_date
  ON ticker_events(ticker, event_date DESC);

ALTER TABLE ticker_events ENABLE ROW LEVEL SECURITY;

-- Lecture publique (les events ne sont pas confidentiels)
DROP POLICY IF EXISTS "ticker_events_read" ON ticker_events;
CREATE POLICY "ticker_events_read" ON ticker_events FOR SELECT USING (true);
