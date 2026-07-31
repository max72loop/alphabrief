-- ============================================================
-- Base miroir — amorçage
-- ============================================================
-- Recrée le contexte que Supabase fournit d'office et qu'un Postgres nu
-- n'a pas. Sans ce fichier, toute migration contenant `TO authenticated`
-- échoue avec « role "authenticated" does not exist » — une faute que le
-- parseur de syntaxe ne peut pas voir, puisque la syntaxe est correcte.
--
-- Cette base est JETABLE et ne contient JAMAIS de donnée réelle.
-- ============================================================

-- Rôles Supabase
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO anon, authenticated, service_role;

-- Schéma `auth` minimal : auth.uid() est référencé par le durcissement
-- optionnel des policies.
CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $$
    SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$ LANGUAGE sql STABLE;
