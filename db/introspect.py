#!/usr/bin/env python3
"""Introspection du schéma Supabase réel, via la spec OpenAPI de PostgREST.

Pourquoi pas pg_dump --schema-only : il faut une connexion Postgres directe
(hôte db.<ref>.supabase.co + mot de passe de la base), et aucun identifiant de
ce type n'existe sur ce VPS. PostgREST expose en revanche une spec OpenAPI
complète, qui décrit chaque table exposée avec ses colonnes, types, valeurs par
défaut, nullabilité et clés — y compris les tables vides, que l'échantillonnage
d'une ligne ne permettait pas de voir.

Deux usages :
    python db/introspect.py --write     regénère db/schema.reference.sql
    python db/introspect.py --drift     diffe la base réelle contre la référence
                                        (sortie non vide = échec, exit 1)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/root/alphabrief")
from config import Config  # noqa: E402

REFERENCE = Path("/root/alphabrief/db/schema.reference.sql")


def fetch_spec() -> dict:
    req = urllib.request.Request(
        f"{Config.SUPABASE_URL}/rest/v1/",
        headers={
            "apikey": Config.SUPABASE_KEY,
            "Authorization": f"Bearer {Config.SUPABASE_KEY}",
            "Accept": "application/openapi+json",
        },
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def tables(spec: dict) -> dict:
    defs = spec.get("definitions") or spec.get("components", {}).get("schemas") or {}
    out = {}
    for name, body in sorted(defs.items()):
        cols = {}
        required = set(body.get("required", []))
        for col, meta in body.get("properties", {}).items():
            desc = meta.get("description", "") or ""
            cols[col] = {
                "type": meta.get("format") or meta.get("type") or "?",
                "nullable": col not in required,
                "pk": "<pk" in desc,
                "fk": "<fk" in desc,
                "default": meta.get("default"),
            }
        out[name] = cols
    return out


def render(t: dict) -> str:
    try:
        commit = subprocess.run(
            ["git", "-C", "/root/alphabrief", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        commit = "inconnu"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "-- ============================================================",
        "-- AlphaBrief — RÉFÉRENCE DE SCHÉMA (constat, pas souhait)",
        "-- ============================================================",
        f"-- Prise le    : {stamp}",
        f"-- Commit      : {commit}",
        "-- Source      : spec OpenAPI de PostgREST sur le projet Supabase",
        "--",
        "-- GÉNÉRÉ — ne pas éditer à la main. Regénérer avec :",
        "--     python db/introspect.py --write",
        "--",
        "-- C'est CE fichier qui alimente la base miroir, plus",
        "-- supabase_schema.sql. Un schéma écrit à la main dérive de la base",
        "-- sans prévenir : c'est ce qui a coûté le bug `recorded_at`.",
        "--",
        "-- Vérifier la dérive à tout moment :  make db-drift",
        "-- ============================================================",
        "",
    ]
    # DDL exécutable : c'est ce fichier qui amorce la base miroir.
    LITTERAL_DEFAULTS = {"now()", "gen_random_uuid()", "CURRENT_DATE", "CURRENT_TIMESTAMP"}
    for name, cols in t.items():
        lines.append(f"-- ── {name} " + "─" * max(0, 48 - len(name)))
        lines.append(f"CREATE TABLE IF NOT EXISTS {name} (")
        w = max((len(c) for c in cols), default=0)
        body = []
        for col, m in cols.items():
            typ = m["type"]
            frag = f"    {col:<{w}}  {typ}"
            if m["default"] is not None:
                d = str(m["default"])
                frag += f" DEFAULT {d if d in LITTERAL_DEFAULTS else repr(d).replace(chr(39)+chr(39), chr(39))}"
            if not m["nullable"]:
                frag += " NOT NULL"
            if m["pk"]:
                frag += " PRIMARY KEY"
            body.append(frag)
        lines.append(",\n".join(body))
        lines.append(");")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--drift", action="store_true")
    a = ap.parse_args()

    live = tables(fetch_spec())

    if a.write:
        REFERENCE.write_text(render(live))
        print(f"référence écrite : {REFERENCE}  ({len(live)} tables)")
        return 0

    if a.drift:
        if not REFERENCE.exists():
            print("ECHEC : db/schema.reference.sql absent — lancer --write")
            return 1
        actuel = render(live).split("\n")
        connu = REFERENCE.read_text().split("\n")
        # On ignore l'en-tête (date et commit changent à chaque prise).
        skip = lambda ls: [l for l in ls if not l.startswith(("-- Prise le", "-- Commit"))]
        import difflib
        d = list(difflib.unified_diff(skip(connu), skip(actuel),
                                      "schema.reference.sql", "base réelle", lineterm=""))
        if d:
            print("DÉRIVE DÉTECTÉE entre la référence et la base réelle :\n")
            print("\n".join(d))
            return 1
        print(f"aucune dérive — {len(live)} tables conformes à la référence")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
