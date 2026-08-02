#!/usr/bin/env python3
"""Prouve que la dernière sauvegarde se restaure vraiment.

    python db/restore_check.py          # ou : make db-restore-check

Une sauvegarde jamais restaurée est une hypothèse, pas une sauvegarde. Le cron
de 03:20 vérifie qu'un fichier non vide est produit — ce qui ne prouve à peu
près rien sur son contenu. Ce script exerce le dernier maillon : il restaure le
dump réellement présent sur le disque dans une base jetable, et regarde ce qui
en sort.

CE QUI FAIT ÉCHOUER (rouge) :
  1. la restauration elle-même renvoie une erreur
  2. le schéma restauré diffère du schéma réel — un dump qui a silencieusement
     perdu une contrainte, un index ou une séquence est pire qu'un dump absent,
     parce qu'il restaure sans se plaindre
  3. une table peuplée en réel ressort vide de la restauration
  4. les assertions sémantiques ne passent pas sur la base restaurée

CE QUI NE FAIT PAS ÉCHOUER (informatif) :
  l'écart de comptage entre le dump et la base réelle. Le dump date de 03:20,
  le scoring de 7h a écrit depuis : `score_history` DOIT avoir plus de lignes
  en réel. Traiter ça comme une anomalie ferait sonner l'alarme tous les jours,
  et une alarme qui sonne toujours ne sert plus à rien.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DB = "alphabrief"
SCRATCH = "alphabrief_restore_check"
BACKUP_DIR = Path("/root/backups/alphabrief-db")
ASSERTIONS = Path(__file__).resolve().parent / "mirror" / "90_assertions.sql"

# Tables dont on sait qu'elles ne font que croître : en réel, elles doivent
# être >= au dump. L'inverse signalerait une perte de données côté réel.
APPEND_ONLY = {"score_history", "ticker_events", "paper_rebalances",
               "paper_nav_history"}


def run(cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def psql_rows(db: str, sql: str) -> list[str]:
    r = run(f'psql -tAX -d {db} -c "{sql}"')
    if r.returncode != 0:
        raise RuntimeError(f"psql sur {db} : {r.stderr.strip()}")
    return [l for l in r.stdout.splitlines() if l.strip()]


def counts(db: str) -> dict[str, int]:
    tables = psql_rows(
        db, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1"
    )
    out = {}
    for t in tables:
        out[t] = int(psql_rows(db, f"SELECT count(*) FROM {t}")[0])
    return out


def schema_of(db: str) -> str:
    r = run(f"pg_dump --schema-only --no-owner --no-privileges -d {db}")
    if r.returncode != 0:
        raise RuntimeError(f"pg_dump sur {db} : {r.stderr.strip()}")
    # pg_dump 16 émet un jeton \restrict aléatoire à chaque exécution.
    return "\n".join(
        l for l in r.stdout.splitlines() if not re.match(r"^\\(un)?restrict ", l)
    )


def alerte_telegram(dump_name: str, failures: list[str]) -> None:
    """Prévient Max. Uniquement avec --notify, donc uniquement depuis le cron :
    une vérification lancée à la main ne doit pas déclencher d'alerte."""
    try:
        sys.path.insert(0, "/root")
        from alfred.shared.telegram import notify, Priority
        detail = "\n".join(f"• {f}" for f in failures)
        notify(
            f"<b>Sauvegarde AlphaBrief non fiable</b>\n"
            f"Dump testé : {dump_name}\n\n{detail}\n\n"
            f"La base porte le patrimoine et c'est la seule copie.",
            priority=Priority.URGENT,
            agent="alphabrief",
        )
    except Exception as e:  # ne jamais masquer l'échec initial derrière celui-ci
        print(f"(alerte Telegram impossible : {e})")


def main() -> int:
    if SCRATCH == DB:
        print(f"REFUS : la base de test vaut la vraie base ({DB}).")
        return 1

    dumps = sorted(BACKUP_DIR.glob("alphabrief_*.sql.gz"))
    if not dumps:
        print(f"ECHEC : aucune sauvegarde dans {BACKUP_DIR}")
        return 1
    dump = dumps[-1]
    size_mb = dump.stat().st_size / 1024 / 1024
    print(f"Sauvegarde testée : {dump.name} ({size_mb:.2f} Mo)")

    failures: list[str] = []
    try:
        # ── 1. Restauration ──────────────────────────────────────────
        run(f'psql -d postgres -c "DROP DATABASE IF EXISTS {SCRATCH}"')
        r = run(f'psql -d postgres -c "CREATE DATABASE {SCRATCH}"')
        if r.returncode != 0:
            print(f"ECHEC : creation de {SCRATCH} — {r.stderr.strip()}")
            return 1

        r = run(f"gunzip -c {dump} | psql -v ON_ERROR_STOP=1 -q -X -d {SCRATCH}")
        if r.returncode != 0:
            failures.append("la restauration a echoue")
            print("\n--- erreur de restauration ---")
            print(r.stderr.strip()[:2000])
        else:
            print("1. restauration        OK")

        if not failures:
            # ── 2. Le schéma restauré est-il le schéma réel ? ─────────
            if schema_of(SCRATCH) == schema_of(DB):
                print("2. schema identique    OK")
            else:
                failures.append("le schema restaure differe du schema reel")
                print("2. schema identique    ECHEC")

            # ── 3. Aucune table peuplée ne ressort vide ───────────────
            c_real, c_restored = counts(DB), counts(SCRATCH)
            vides, ecarts = [], []
            for table, n_real in sorted(c_real.items()):
                n_res = c_restored.get(table, 0)
                if n_real > 0 and n_res == 0:
                    vides.append(f"{table} : {n_real} en reel, 0 restauree")
                elif table in APPEND_ONLY and n_res > n_real:
                    ecarts.append(
                        f"{table} : {n_res} dans le dump > {n_real} en reel "
                        f"(table append-only : perte de donnees cote reel ?)"
                    )
            if vides:
                failures.extend(vides)
                print("3. tables peuplees     ECHEC")
            else:
                print("3. tables peuplees     OK")
            failures.extend(ecarts)

            # ── 4. Assertions sémantiques sur la base restaurée ───────
            r = run(f"psql -v ON_ERROR_STOP=1 -q -X -d {SCRATCH} -f {ASSERTIONS}")
            if r.returncode == 0:
                print("4. assertions          OK")
            else:
                failures.append("les assertions echouent sur la base restauree")
                print("4. assertions          ECHEC")
                print(r.stderr.strip()[:1500])

            # ── Écarts de comptage : information, pas alarme ──────────
            print("\nEcarts de comptage (attendus — le dump precede le scoring) :")
            for table, n_real in sorted(c_real.items()):
                n_res = c_restored.get(table, 0)
                if n_res != n_real:
                    print(f"  {table:26} dump {n_res:>6}   reel {n_real:>6}"
                          f"   (+{n_real - n_res})")
    finally:
        run(f'psql -d postgres -c "DROP DATABASE IF EXISTS {SCRATCH}"')

    print()
    if failures:
        print("SAUVEGARDE NON FIABLE :")
        for f in failures:
            print(f"  - {f}")
        if "--notify" in sys.argv:
            alerte_telegram(dump.name, failures)
        return 1
    print(f"SAUVEGARDE VERIFIEE — {dump.name} se restaure a l'identique.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
