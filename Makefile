.PHONY: db-apply db-reset db-check db-diff db-backup db-shell db-shell-mirror help

# ── Bases ───────────────────────────────────────────────────
# DB     : la vraie. Contient le patrimoine. Jamais détruite par une cible.
# MIRROR : jetable, sans aucune donnée réelle. Autonomie totale dessus.
DB          ?= alphabrief
MIRROR_DB   ?= alphabrief_mirror
REPO        := $(shell pwd)

PSQL        := psql -v ON_ERROR_STOP=1 -X -q
PSQL_DB     := $(PSQL) -d $(DB)
PSQL_MIRROR := $(PSQL) -d $(MIRROR_DB)

# Le schéma, dans l'ordre. Les deux bases partent des mêmes fichiers : c'est
# ce qui fait de la miroir une répétition fidèle et non une approximation.
SCHEMA := $(REPO)/db/schema.sql $(REPO)/migrations/2026_07_31_patrimoine_schema.sql

help:
	@echo "db-apply    applique le schema sur la VRAIE base (idempotent, ne detruit rien)"
	@echo "db-reset    recree la miroir depuis zero et rejoue le schema deux fois"
	@echo "db-check    rejoue les assertions sur la miroir existante"
	@echo "db-diff     compare le DDL reel de la vraie base a celui de la miroir"
	@echo "db-backup   pg_dump horodate de la vraie base vers /root/backups"
	@echo "db-shell    psql sur la vraie base"

# Garde-fou : db-reset fait un DROP DATABASE. Si MIRROR_DB pointait un jour
# sur la vraie base — surcharge en ligne de commande, faute de frappe — la
# commande détruirait le patrimoine. La cible refuse de tourner dans ce cas.
guard-mirror:
	@if [ "$(MIRROR_DB)" = "$(DB)" ]; then \
		echo "REFUS : MIRROR_DB vaut '$(MIRROR_DB)', soit la vraie base. Rien n'a ete fait."; \
		exit 1; \
	fi

# ── La vraie base ───────────────────────────────────────────
# Uniquement des CREATE IF NOT EXISTS / ALTER idempotents : rejouable sans
# effet de bord, et incapable de supprimer une table ou des données.
db-apply:
	@echo "── schema sur $(DB) ─────────────────────────────────"
	@for f in $(SCHEMA); do $(PSQL_DB) -f $$f; done
	@echo "APPLIQUE sur $(DB)"

# ── La miroir ───────────────────────────────────────────────
db-reset: guard-mirror
	@echo "── 1/4  base jetable ────────────────────────────────"
	@$(PSQL) -d postgres -c "DROP DATABASE IF EXISTS $(MIRROR_DB);"
	@$(PSQL) -d postgres -c "CREATE DATABASE $(MIRROR_DB);"
	@echo "── 2/4  schema ──────────────────────────────────────"
	@for f in $(SCHEMA); do $(PSQL_MIRROR) -f $$f; done
	@echo "── 3/4  assertions ──────────────────────────────────"
	@$(PSQL_MIRROR) -f $(REPO)/db/mirror/90_assertions.sql
	@echo "── 4/4  idempotence : on rejoue tout ────────────────"
	@for f in $(SCHEMA); do $(PSQL_MIRROR) -f $$f; done
	@$(PSQL_MIRROR) -f $(REPO)/db/mirror/90_assertions.sql
	@echo ""
	@echo "MIROIR AU VERT (schema rejouable)"

db-check:
	@$(PSQL_MIRROR) -f $(REPO)/db/mirror/90_assertions.sql

# ── Dérive ──────────────────────────────────────────────────
# Remplace l'ancien `db-drift`, qui interrogeait la spec OpenAPI de PostgREST
# et ne voyait ni les contraintes UNIQUE hors PK, ni les FK, ni les CHECK, ni
# les index, ni les triggers, ni les SÉQUENCES — c'est cet angle mort qui a
# failli coûter une violation de clé primaire à la reprise.
#
# Maintenant que la base est locale, pg_dump donne le DDL réel et complet.
# La comparaison est donc exhaustive au lieu d'être partielle.
#
# Le filtre `\restrict` n'est pas une commodité : pg_dump 16 émet un jeton
# aléatoire à chaque exécution, donc sans lui le diff n'est JAMAIS vide et
# l'outil crierait à la dérive à tous les coups — le meilleur moyen de rendre
# une alarme inutile est de la faire sonner en permanence.
db-diff: guard-mirror
	@$(MAKE) --no-print-directory db-reset > /dev/null
	@pg_dump --schema-only --no-owner --no-privileges -d $(DB) \
		| grep -vE '^\\(un)?restrict ' > /tmp/ab_reel.sql
	@pg_dump --schema-only --no-owner --no-privileges -d $(MIRROR_DB) \
		| grep -vE '^\\(un)?restrict ' > /tmp/ab_attendu.sql
	@if diff -u /tmp/ab_attendu.sql /tmp/ab_reel.sql; then \
		echo "aucune derive — la vraie base est conforme au schema du depot"; \
	else \
		echo ""; \
		echo "DERIVE detectee (gauche = ce que dit le depot, droite = la vraie base)"; \
		exit 1; \
	fi

# ── Sauvegarde ──────────────────────────────────────────────
# Ce qui remplace les backups managés de Supabase. Hors du dépôt.
db-backup:
	@mkdir -p /root/backups/alphabrief-db
	@f=/root/backups/alphabrief-db/alphabrief_$$(date +%Y%m%d_%H%M%S).sql.gz; \
	pg_dump --no-owner --no-privileges -d $(DB) | gzip > $$f && \
	if [ ! -s $$f ]; then echo "ECHEC : dump vide, $$f supprime"; rm -f $$f; exit 1; fi && \
	echo "sauvegarde : $$f ($$(du -h $$f | cut -f1))"
	@# Rétention 30 jours. Faite ICI et pas dans le cron : une politique de
	@# rétention cachée dans une ligne de crontab est invisible à la relecture
	@# du dépôt, et c'est comme ça qu'on garde 4 ans de dumps ou zéro.
	@ls -1t /root/backups/alphabrief-db/alphabrief_*.sql.gz 2>/dev/null \
		| tail -n +31 | xargs -r rm --
	@echo "$$(ls -1 /root/backups/alphabrief-db/*.sql.gz 2>/dev/null | wc -l) sauvegarde(s) conservee(s)"

db-shell:
	@psql -d $(DB)

db-shell-mirror:
	@psql -d $(MIRROR_DB)
