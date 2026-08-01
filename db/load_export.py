#!/usr/bin/env python3
"""Reprise des données Supabase dans le Postgres local.

    python db/load_export.py /root/backups/alphabrief_supabase_20260801

Idempotent : chaque table est vidée avant rechargement, donc rejouable
autant de fois que nécessaire tant que la reprise n'est pas figée.

TROIS POINTS QUI FONT ÉCHOUER UNE REPRISE NAÏVE, traités ici :

1. L'ORDRE. watchlist_tickers référence watchlists, les 7 tables paper_*
   référencent paper_portfolios. Chargées dans l'ordre alphabétique du
   dossier, elles échouent en violation de clé étrangère.

2. LES SÉQUENCES. Les colonnes `id` sont des identités : insérer les lignes
   avec leur id explicite ne fait PAS avancer le compteur. Sans le `setval`
   final, le premier INSERT du daemon réutiliserait l'id 1 et planterait en
   violation de clé primaire — des mois plus tard, sans rapport apparent.

3. LES TABLES SaaS. profiles / api_usage / user_scans sont exportées (le
   backup doit être complet) mais délibérément pas rechargées : elles
   n'existent plus dans le schéma cible. Voir db/schema.sql.
"""
import json
import sys
from pathlib import Path

import psycopg

# Ordre de chargement : les référencées avant celles qui les référencent.
ORDER = [
    "ticker_scores",
    "score_history",
    "ticker_events",
    "watchlists",
    "watchlist_tickers",
    "paper_portfolios",
    "paper_positions",
    "paper_rebalances",
    "paper_nav_history",
    "paper_metrics",
    "paper_missed_rebalances",
    "paper_corporate_actions",
    "paper_sofr_rates",
]

# Exportées pour la complétude du backup, hors du schéma cible.
SKIP = {"profiles", "api_usage", "user_scans"}


def main(src: Path) -> int:
    report, mismatches = [], []

    with psycopg.connect("dbname=alphabrief", autocommit=False) as conn:
        with conn.cursor() as cur:
            # Les triggers append-only bloquent le DELETE de purge.
            cur.execute("SET session_replication_role = replica;")

            for table in ORDER:
                path = src / f"{table}.json"
                if not path.exists():
                    mismatches.append(f"{table}: export absent ({path})")
                    continue
                rows = json.loads(path.read_text())

                cur.execute(f"DELETE FROM {table};")
                if rows:
                    cols = list(rows[0].keys())
                    collist = ", ".join(f'"{c}"' for c in cols)
                    marks = ", ".join(["%s"] * len(cols))
                    values = [
                        tuple(
                            json.dumps(r[c]) if isinstance(r[c], (dict, list)) else r[c]
                            for c in cols
                        )
                        for r in rows
                    ]
                    cur.executemany(
                        f"INSERT INTO {table} ({collist}) VALUES ({marks})", values
                    )

                cur.execute(f"SELECT count(*) FROM {table};")
                got = cur.fetchone()[0]
                if got != len(rows):
                    mismatches.append(f"{table}: {got} en base / {len(rows)} exportées")
                report.append(f"{table:28} {got:>6} lignes")

                # Recaler la séquence sur le max réel.
                #
                # La garde sur information_schema n'est pas décorative :
                # paper_metrics a pour clé `portfolio_id` et paper_sofr_rates
                # `date`. Sur une table sans colonne `id`,
                # pg_get_serial_sequence ne renvoie pas NULL, il LÈVE
                # UndefinedColumn — et fait échouer toute la reprise.
                cur.execute(
                    "SELECT 1 FROM information_schema.columns "
                    " WHERE table_schema='public' AND table_name=%s "
                    "   AND column_name='id'",
                    (table,),
                )
                if not cur.fetchone():
                    continue
                cur.execute(
                    "SELECT pg_get_serial_sequence(%s, 'id')", (f"public.{table}",)
                )
                seq = cur.fetchone()[0]
                if seq:
                    cur.execute(
                        f"SELECT setval(%s, COALESCE((SELECT max(id) FROM {table}), 1), "
                        f"(SELECT count(*) FROM {table}) > 0)",
                        (seq,),
                    )

            cur.execute("SET session_replication_role = DEFAULT;")
        conn.commit()

    print("\n".join(report))
    print(f"\nTotal : {sum(int(l.split()[1]) for l in report)} lignes")
    for t in sorted(SKIP):
        print(f"ignorée (hors schéma cible) : {t}")

    if mismatches:
        print("\nECARTS :\n  " + "\n  ".join(mismatches))
        return 1
    print("\nReprise conforme — chaque table correspond à son export.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1])))
