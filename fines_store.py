"""Transactional local fines ledger. Amounts are stored as integer DKK."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

RULES = [('Dobbeltfejl', 10), ('For sent til træning', 20), ('For sent til kamp', 50),
         ('Glemt udstyr til træning', 20), ('Glemt udstyr til kamp', 50),
         ('Glemt bat', 100), ('Glemt holdtrøje til kamp', 50),
         ('For sent afbud til kamp', 50), ('Udeblivelse fra kamp', 100), ('Tabt sæt 6-0', 50)]


@contextmanager
def database():
    path = Path(os.environ.get('PADEL_FINES_DB', Path(__file__).parent / 'data' / 'fines.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        with con:
            con.execute('CREATE TABLE IF NOT EXISTS rules (name TEXT PRIMARY KEY, amount INTEGER NOT NULL CHECK(amount > 0))')
            con.execute('''CREATE TABLE IF NOT EXISTS fines (
                id TEXT PRIMARY KEY, created TEXT NOT NULL, player TEXT NOT NULL,
                reason TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount > 0),
                cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0, 1)))''')
            # Seed once, so subsequent rate changes survive restarts.
            con.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY)')
            if not con.execute("SELECT 1 FROM metadata WHERE key='seeded'").fetchone():
                con.executemany('INSERT OR IGNORE INTO rules VALUES (?, ?)', RULES)
                con.execute("INSERT INTO metadata VALUES ('seeded')")
            yield con
    finally:
        con.close()


def snapshot():
    with database() as con:
        return {key: [dict(r) for r in con.execute(query)] for key, query in {
            'rules': 'SELECT * FROM rules ORDER BY rowid',
            'fines': 'SELECT * FROM fines ORDER BY created DESC, rowid DESC',
        }.items()}


def give_fine(player, reason, roster, request_id=None):
    with database() as con:
        if player not in roster:
            raise ValueError('Ukendt spiller')
        rule = con.execute('SELECT amount FROM rules WHERE name=?', (reason,)).fetchone()
        if rule is None:
            raise ValueError('Ukendt bødetype')
        fine_id = request_id or str(uuid4())
        con.execute('INSERT INTO fines (id, created, player, reason, amount) VALUES (?, ?, ?, ?, ?)',
                    (fine_id, datetime.now(timezone.utc).isoformat(), player, reason, rule['amount']))
        return fine_id, rule['amount']


def set_cancelled(fine_id, cancelled):
    with database() as con:
        con.execute('UPDATE fines SET cancelled=? WHERE id=?', (int(bool(cancelled)), fine_id))


def update_rate(reason, amount):
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError('Satsen skal være et positivt helt antal kroner')
    with database() as con:
        con.execute('UPDATE rules SET amount=? WHERE name=?', (amount, reason))
