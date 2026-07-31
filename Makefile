.PHONY: db-reset db-shell db-policies db-check db-drift db-reference help

# ── Base miroir ─────────────────────────────────────────────
# Postgres local, JETABLE, sans aucune donnée réelle. Autonomie totale
# dessus ; aucune sur Supabase (voir CLAUDE.md, « Frontière d'autonomie »).
MIRROR_DB   ?= alphabrief_mirror
PSQL        := sudo -u postgres psql -v ON_ERROR_STOP=1 -X -q
PSQL_DB     := sudo -u postgres psql -v ON_ERROR_STOP=1 -X -q -d $(MIRROR_DB)
REPO        := $(shell pwd)

help:
	@echo "db-reset    recree la miroir depuis zero et rejoue toutes les migrations"
	@echo "db-check    rejoue seulement les assertions sur la miroir existante"
	@echo "db-policies affiche pg_policies (meme requete qu'en prod)"
	@echo "db-drift    diffe la base reelle contre db/schema.reference.sql"
	@echo "db-reference regenere la reference depuis la base reelle"
	@echo "db-shell    psql sur la miroir"

# Rejouable depuis une base vide jusqu'à l'état cible, en une commande.
# Échoue au premier problème : ON_ERROR_STOP partout.
db-reset:
	@echo "── 1/7  base jetable ────────────────────────────────"
	@$(PSQL) -c "DROP DATABASE IF EXISTS $(MIRROR_DB);"
	@$(PSQL) -c "CREATE DATABASE $(MIRROR_DB);"
	@echo "── 2/7  bootstrap (roles Supabase, schema auth) ─────"
	@$(PSQL_DB) -f $(REPO)/db/mirror/00_bootstrap.sql
	@echo "── 3/7  schema REEL (db/schema.reference.sql, introspecte) ─"
	@$(PSQL_DB) -f $(REPO)/db/schema.reference.sql
	@$(PSQL_DB) -f $(REPO)/db/mirror/05_contraintes_connues.sql
	@$(PSQL_DB) -f $(REPO)/db/mirror/10_policies_initiales.sql
	@echo "── 4/7  migrations du pivot, dans l'ordre ───────────"
	@$(PSQL_DB) -f $(REPO)/migrations/2026_07_31_close_public_rls.sql
	@$(PSQL_DB) -f $(REPO)/migrations/2026_07_31_patrimoine_schema.sql
	@echo "── 5/7  assertions ──────────────────────────────────"
	@$(PSQL_DB) -f $(REPO)/db/mirror/90_assertions.sql
	@echo "── 6/7  partage par role (lecture/ecriture reelles) ─"
	@$(PSQL_DB) -f $(REPO)/db/mirror/91_roles.sql
	@echo "── 7/7  idempotence : rejeu des migrations ──────────"
	@$(PSQL_DB) -f $(REPO)/migrations/2026_07_31_close_public_rls.sql
	@$(PSQL_DB) -f $(REPO)/migrations/2026_07_31_patrimoine_schema.sql
	@$(PSQL_DB) -f $(REPO)/db/mirror/90_assertions.sql
	@echo ""
	@echo "MIROIR AU VERT (migrations rejouables)"

db-check:
	@$(PSQL_DB) -f $(REPO)/db/mirror/90_assertions.sql
	@$(PSQL_DB) -f $(REPO)/db/mirror/91_roles.sql

# Diffe la base REELLE contre db/schema.reference.sql. Sortie non vide = echec.
db-drift:
	@python3 $(REPO)/db/introspect.py --drift

# Regenere la reference depuis la base reelle (a faire apres toute migration
# appliquee en prod, sinon db-drift criera a tort).
db-reference:
	@python3 $(REPO)/db/introspect.py --write

db-policies:
	@$(PSQL_DB) -c "SELECT tablename, policyname, roles, cmd \
	                  FROM pg_policies WHERE schemaname='public' \
	                 ORDER BY (roles::text[] && ARRAY['public','anon']) DESC, tablename, cmd;"

db-shell:
	@sudo -u postgres psql -d $(MIRROR_DB)
