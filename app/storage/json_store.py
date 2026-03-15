import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import current_app

DEFAULT_SECTIONS = ['identity', 'business', 'signal', 'price_levels', 'score', 'market', 'fundamentals', 'risk', 'technicals']


class JsonStore:
    """Abstraction layer for SQLite storage. All data access goes through here.
    Public interface is unchanged from the previous JSON-based implementation.
    """

    @staticmethod
    def _db_path() -> Path:
        return current_app.config['DB_PATH']

    @classmethod
    @contextmanager
    def _conn(cls):
        db_path = cls._db_path()
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    # ─────────────────────────────────────────────
    # Init (called once at app startup)
    # ─────────────────────────────────────────────

    @classmethod
    def init_db(cls, app) -> None:
        """Create tables, enable WAL, and migrate existing JSON data."""
        db_path = app.config['DB_PATH']
        db_path.parent.mkdir(parents=True, exist_ok=True)

        con = sqlite3.connect(str(db_path))
        con.execute('PRAGMA journal_mode=WAL')
        con.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS portfolio (
                ticker    TEXT PRIMARY KEY,
                quantity  REAL NOT NULL DEFAULT 0,
                buy_price REAL NOT NULL DEFAULT 0,
                added_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scores_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker     TEXT NOT NULL,
                score      INTEGER NOT NULL,
                confidence INTEGER NOT NULL,
                date       TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_scores_ticker ON scores_history(ticker);

            CREATE TABLE IF NOT EXISTS card_cache (
                ticker       TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                card_json    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ui_preferences (
                ticker        TEXT PRIMARY KEY,
                sections_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker     TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                score_old  INTEGER,
                score_new  INTEGER NOT NULL,
                message    TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read       INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alerts(ticker);

            CREATE TABLE IF NOT EXISTS pools (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                color      TEXT NOT NULL DEFAULT '#6366f1',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pool_tickers (
                pool_id INTEGER NOT NULL REFERENCES pools(id) ON DELETE CASCADE,
                ticker  TEXT NOT NULL,
                PRIMARY KEY (pool_id, ticker)
            );
        """)
        con.commit()
        con.close()

        data_dir = app.config['DATA_DIR']
        cls._migrate_json(data_dir, db_path)

    @classmethod
    def _migrate_json(cls, data_dir: Path, db_path: Path) -> None:
        """One-time migration from JSON files to SQLite. Renames files to .bak after."""
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row

        # watchlist.json
        wl_path = data_dir / 'watchlist.json'
        if wl_path.exists():
            try:
                data = json.loads(wl_path.read_text(encoding='utf-8'))
                for ticker in data.get('tickers', []):
                    con.execute('INSERT OR IGNORE INTO watchlist VALUES (?)', (ticker.upper(),))
                con.commit()
                wl_path.rename(wl_path.with_suffix('.json.bak'))
            except Exception:
                pass

        # portfolio.json
        pf_path = data_dir / 'portfolio.json'
        if pf_path.exists():
            try:
                data = json.loads(pf_path.read_text(encoding='utf-8'))
                for h in data.get('holdings', []):
                    con.execute(
                        'INSERT OR IGNORE INTO portfolio(ticker, quantity, buy_price, added_at) VALUES (?,?,?,?)',
                        (h['ticker'].upper(), h.get('quantity', 0), h.get('buy_price', 0), h.get('added_at', ''))
                    )
                con.commit()
                pf_path.rename(pf_path.with_suffix('.json.bak'))
            except Exception:
                pass

        # scores_history.json
        sh_path = data_dir / 'scores_history.json'
        if sh_path.exists():
            try:
                data = json.loads(sh_path.read_text(encoding='utf-8'))
                rows = [
                    (e['ticker'].upper(), e.get('score', 0), e.get('confidence', 0), e.get('date', ''))
                    for e in data.get('entries', [])
                ]
                con.executemany(
                    'INSERT INTO scores_history(ticker, score, confidence, date) VALUES (?,?,?,?)',
                    rows
                )
                con.commit()
                sh_path.rename(sh_path.with_suffix('.json.bak'))
            except Exception:
                pass

        # card_cache.json
        cc_path = data_dir / 'card_cache.json'
        if cc_path.exists():
            try:
                data = json.loads(cc_path.read_text(encoding='utf-8'))
                for ticker, entry in data.items():
                    con.execute(
                        'INSERT OR REPLACE INTO card_cache(ticker, generated_at, card_json) VALUES (?,?,?)',
                        (ticker.upper(), entry.get('generated_at', ''), json.dumps(entry.get('card', {})))
                    )
                con.commit()
                cc_path.rename(cc_path.with_suffix('.json.bak'))
            except Exception:
                pass

        # ui_preferences.json
        up_path = data_dir / 'ui_preferences.json'
        if up_path.exists():
            try:
                data = json.loads(up_path.read_text(encoding='utf-8'))
                for ticker, sections in data.get('layouts', {}).items():
                    con.execute(
                        'INSERT OR REPLACE INTO ui_preferences(ticker, sections_json) VALUES (?,?)',
                        (ticker.upper(), json.dumps(sections))
                    )
                con.commit()
                up_path.rename(up_path.with_suffix('.json.bak'))
            except Exception:
                pass

        con.close()

    # ─────────────────────────────────────────────
    # WATCHLIST
    # ─────────────────────────────────────────────

    @classmethod
    def get_watchlist(cls) -> List[str]:
        with cls._conn() as con:
            rows = con.execute('SELECT ticker FROM watchlist').fetchall()
        return [r['ticker'] for r in rows]

    @classmethod
    def add_to_watchlist(cls, ticker: str) -> bool:
        t = ticker.upper()
        with cls._conn() as con:
            cur = con.execute('INSERT OR IGNORE INTO watchlist VALUES (?)', (t,))
        return cur.rowcount > 0

    @classmethod
    def remove_from_watchlist(cls, ticker: str) -> bool:
        t = ticker.upper()
        with cls._conn() as con:
            cur = con.execute('DELETE FROM watchlist WHERE ticker = ?', (t,))
        return cur.rowcount > 0

    # ─────────────────────────────────────────────
    # PORTFOLIO
    # ─────────────────────────────────────────────

    @classmethod
    def get_portfolio(cls) -> List[Dict[str, Any]]:
        with cls._conn() as con:
            rows = con.execute('SELECT ticker, quantity, buy_price, added_at FROM portfolio').fetchall()
        return [dict(r) for r in rows]

    @classmethod
    def add_to_portfolio(cls, ticker: str, quantity: float = 0, buy_price: float = 0) -> bool:
        t = ticker.upper()
        added_at = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        with cls._conn() as con:
            cur = con.execute(
                'INSERT OR IGNORE INTO portfolio(ticker, quantity, buy_price, added_at) VALUES (?,?,?,?)',
                (t, quantity, buy_price, added_at)
            )
        return cur.rowcount > 0

    @classmethod
    def update_holding(cls, ticker: str, quantity: float, buy_price: float) -> bool:
        t = ticker.upper()
        with cls._conn() as con:
            cur = con.execute(
                'UPDATE portfolio SET quantity = ?, buy_price = ? WHERE ticker = ?',
                (quantity, buy_price, t)
            )
        return cur.rowcount > 0

    @classmethod
    def remove_from_portfolio(cls, ticker: str) -> bool:
        t = ticker.upper()
        with cls._conn() as con:
            cur = con.execute('DELETE FROM portfolio WHERE ticker = ?', (t,))
        return cur.rowcount > 0

    # ─────────────────────────────────────────────
    # SCORES HISTORY
    # ─────────────────────────────────────────────

    @classmethod
    def get_score_history(cls, ticker: Optional[str] = None) -> List[Dict[str, Any]]:
        with cls._conn() as con:
            if ticker:
                rows = con.execute(
                    'SELECT ticker, score, confidence, date FROM scores_history WHERE ticker = ? ORDER BY date DESC',
                    (ticker.upper(),)
                ).fetchall()
            else:
                rows = con.execute(
                    'SELECT ticker, score, confidence, date FROM scores_history ORDER BY date DESC'
                ).fetchall()
        return [dict(r) for r in rows]

    @classmethod
    def add_score_entry(cls, ticker: str, score: int, confidence: int) -> None:
        date = datetime.now(timezone.utc).isoformat()
        with cls._conn() as con:
            con.execute(
                'INSERT INTO scores_history(ticker, score, confidence, date) VALUES (?,?,?,?)',
                (ticker.upper(), score, confidence, date)
            )

    @classmethod
    def get_smoothed_score(cls, ticker: str, n: int = 5) -> Optional[float]:
        """Return average score over the last n entries for this ticker."""
        t = ticker.upper()
        with cls._conn() as con:
            rows = con.execute(
                'SELECT score FROM scores_history WHERE ticker = ? ORDER BY date DESC LIMIT ?',
                (t, n)
            ).fetchall()
        if not rows:
            return None
        scores = [r['score'] for r in rows]
        return round(sum(scores) / len(scores), 1)

    # ─────────────────────────────────────────────
    # CARD CACHE
    # ─────────────────────────────────────────────

    @classmethod
    def get_cached_card(cls, ticker: str, max_age_hours: int = 2) -> Optional[Dict[str, Any]]:
        """Return a cached card if it exists and is younger than max_age_hours, else None."""
        t = ticker.upper()
        with cls._conn() as con:
            row = con.execute(
                'SELECT generated_at, card_json FROM card_cache WHERE ticker = ?', (t,)
            ).fetchone()
        if not row:
            return None
        try:
            generated_at = datetime.fromisoformat(row['generated_at'])
            if datetime.now(timezone.utc) - generated_at < timedelta(hours=max_age_hours):
                return json.loads(row['card_json'])
        except (ValueError, json.JSONDecodeError):
            pass
        return None

    @classmethod
    def save_cached_card(cls, ticker: str, card: Dict[str, Any]) -> None:
        t = ticker.upper()
        generated_at = datetime.now(timezone.utc).isoformat()
        with cls._conn() as con:
            con.execute(
                'INSERT OR REPLACE INTO card_cache(ticker, generated_at, card_json) VALUES (?,?,?)',
                (t, generated_at, json.dumps(card, ensure_ascii=False))
            )

    @classmethod
    def get_ticker_names(cls, tickers: list) -> dict:
        """Return {ticker: company_name} from card_cache, no age check (name doesn't expire)."""
        if not tickers:
            return {}
        uppers = [t.upper() for t in tickers]
        placeholders = ','.join('?' * len(uppers))
        with cls._conn() as con:
            rows = con.execute(
                f'SELECT ticker, card_json FROM card_cache WHERE ticker IN ({placeholders})',
                uppers
            ).fetchall()
        result = {}
        for row in rows:
            try:
                card = json.loads(row['card_json'])
                name = card.get('identity', {}).get('name')
                if name:
                    result[row['ticker']] = name
            except (json.JSONDecodeError, KeyError):
                pass
        return result

    @classmethod
    def invalidate_card_cache(cls, ticker: str) -> None:
        t = ticker.upper()
        with cls._conn() as con:
            con.execute('DELETE FROM card_cache WHERE ticker = ?', (t,))

    # ─────────────────────────────────────────────
    # UI PREFERENCES
    # ─────────────────────────────────────────────

    @classmethod
    def get_layout(cls, ticker: str) -> List[str]:
        t = ticker.upper()
        with cls._conn() as con:
            row = con.execute(
                'SELECT sections_json FROM ui_preferences WHERE ticker = ?', (t,)
            ).fetchone()
        if not row:
            return DEFAULT_SECTIONS[:]
        try:
            return json.loads(row['sections_json'])
        except json.JSONDecodeError:
            return DEFAULT_SECTIONS[:]

    @classmethod
    def save_layout(cls, ticker: str, sections: List[str]) -> None:
        t = ticker.upper()
        with cls._conn() as con:
            con.execute(
                'INSERT OR REPLACE INTO ui_preferences(ticker, sections_json) VALUES (?,?)',
                (t, json.dumps(sections))
            )

    # ─────────────────────────────────────────────
    # ALERTS
    # ─────────────────────────────────────────────

    @classmethod
    def get_alerts(cls, unread_only: bool = False) -> List[Dict[str, Any]]:
        with cls._conn() as con:
            if unread_only:
                rows = con.execute(
                    'SELECT * FROM alerts WHERE read = 0 ORDER BY created_at DESC'
                ).fetchall()
            else:
                rows = con.execute(
                    'SELECT * FROM alerts ORDER BY created_at DESC'
                ).fetchall()
        return [dict(r) for r in rows]

    @classmethod
    def add_alert(cls, ticker: str, alert_type: str, score_old: Optional[int],
                  score_new: int, message: str) -> None:
        t = ticker.upper()
        created_at = datetime.now(timezone.utc).isoformat()
        with cls._conn() as con:
            # Déduplication STRONG_BUY : skip si déjà alerté dans les 24h
            if alert_type == 'STRONG_BUY':
                cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                existing = con.execute(
                    'SELECT id FROM alerts WHERE ticker = ? AND alert_type = ? AND created_at > ?',
                    (t, 'STRONG_BUY', cutoff)
                ).fetchone()
                if existing:
                    return
            con.execute(
                'INSERT INTO alerts(ticker, alert_type, score_old, score_new, message, created_at) '
                'VALUES (?,?,?,?,?,?)',
                (t, alert_type, score_old, score_new, message, created_at)
            )

    @classmethod
    def mark_alerts_read(cls) -> None:
        with cls._conn() as con:
            con.execute('UPDATE alerts SET read = 1 WHERE read = 0')

    @classmethod
    def get_unread_count(cls) -> int:
        with cls._conn() as con:
            row = con.execute('SELECT COUNT(*) FROM alerts WHERE read = 0').fetchone()
        return row[0] if row else 0

    # ─────────────────────────────────────────────
    # POOLS
    # ─────────────────────────────────────────────

    @classmethod
    def get_pools(cls) -> List[Dict[str, Any]]:
        with cls._conn() as con:
            rows = con.execute('SELECT id, name, color, created_at FROM pools ORDER BY created_at').fetchall()
        return [dict(r) for r in rows]

    @classmethod
    def create_pool(cls, name: str, color: str = '#6366f1') -> Optional[int]:
        created_at = datetime.now(timezone.utc).isoformat()
        with cls._conn() as con:
            try:
                cur = con.execute(
                    'INSERT INTO pools(name, color, created_at) VALUES (?,?,?)',
                    (name.strip(), color, created_at)
                )
                return cur.lastrowid
            except Exception:
                return None

    @classmethod
    def delete_pool(cls, pool_id: int) -> bool:
        with cls._conn() as con:
            cur = con.execute('DELETE FROM pools WHERE id = ?', (pool_id,))
        return cur.rowcount > 0

    @classmethod
    def get_pool_tickers(cls, pool_id: int) -> List[str]:
        with cls._conn() as con:
            rows = con.execute(
                'SELECT ticker FROM pool_tickers WHERE pool_id = ?', (pool_id,)
            ).fetchall()
        return [r['ticker'] for r in rows]

    @classmethod
    def add_ticker_to_pool(cls, pool_id: int, ticker: str) -> bool:
        t = ticker.upper()
        with cls._conn() as con:
            try:
                cur = con.execute(
                    'INSERT OR IGNORE INTO pool_tickers(pool_id, ticker) VALUES (?,?)',
                    (pool_id, t)
                )
                return cur.rowcount > 0
            except Exception:
                return False

    @classmethod
    def remove_ticker_from_pool(cls, pool_id: int, ticker: str) -> bool:
        t = ticker.upper()
        with cls._conn() as con:
            cur = con.execute(
                'DELETE FROM pool_tickers WHERE pool_id = ? AND ticker = ?', (pool_id, t)
            )
        return cur.rowcount > 0
