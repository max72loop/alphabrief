"""Accès au Postgres local d'AlphaBrief.

Remplace le client Supabase. La base tourne sur la même machine que ce code et
n'écoute que localhost ; la connexion se fait par socket Unix sous l'identité
de l'utilisateur système.

CONSÉQUENCE VOULUE : il n'y a ici ni URL, ni clé, ni mot de passe, ni variable
d'environnement obligatoire. Rien à stocker, donc rien à faire fuiter et rien
à faire tourner. C'est ce qui remplace la clé `service_role` que quatre
process se partageaient via /root/.env.

Le DSN reste surchargeable par ALPHABRIEF_DSN — c'est ce qui permet de jouer
les tests contre la base miroir sans toucher aux données réelles.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get("ALPHABRIEF_DSN", "dbname=alphabrief")


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """Connexion transactionnelle : commit à la sortie, rollback si ça lève."""
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        yield conn


def query(sql: str, params: Sequence[Any] = ()) -> list[dict]:
    """Lecture. Renvoie une liste de dicts (colonnes nommées)."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def query_one(sql: str, params: Sequence[Any] = ()) -> Optional[dict]:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Écriture unitaire. Renvoie le nombre de lignes touchées."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount
