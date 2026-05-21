-- AlphaBrief : table d'historique des scores quotidiens.
-- Cible : Supabase project drvahnjprbteactbnlvv (public schema).
-- Inséré par app/storage/supabase_writer.py:write_score() après chaque scoring.
-- À coller dans Supabase Studio > SQL Editor puis Run.

create table if not exists public.score_history (
  id           bigint generated always as identity primary key,
  ticker       text        not null,
  score        numeric     not null,
  confidence   numeric     not null default 0,
  recorded_at  timestamptz not null default now()
);

-- Lookups "dernière trajectoire d'un ticker" sur 30/90j.
create index if not exists score_history_ticker_recorded_idx
  on public.score_history (ticker, recorded_at desc);

-- Le writer utilise l'anon key. Aligner sur ticker_scores : RLS off pour
-- laisser le daemon insérer sans policy. Réactiver + écrire une policy
-- "insert with check (true)" si tu préfères garder RLS partout.
alter table public.score_history disable row level security;
