"""SQL direto, sem ORM. SQLite local ou PostgreSQL pela variável DATABASE_URL."""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent

def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))

load_env()

class Database:
    def __init__(self, url=None):
        self.url = os.getenv('DATABASE_URL', '') if url is None else url
        self.postgres = self.url.startswith(('postgres://', 'postgresql://'))
        if self.url and not self.postgres:
            raise ValueError('DATABASE_URL deve ser uma URL PostgreSQL ou ficar vazia para SQLite.')
        self.path = Path(os.getenv('SQLITE_PATH', str(ROOT / 'data' / 'arremate.db')))

    def connect(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10)
            conn.execute('SET search_path TO arremate, public')
            return conn
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=15000')
        return conn

    @contextmanager
    def transaction(self, write=False):
        conn = self.connect()
        try:
            if self.postgres:
                # Uma transação lê um retrato consistente; escritas são serializadas.
                if write:
                    conn.execute('SELECT id FROM meta WHERE id=1 FOR UPDATE')
                else:
                    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            else:
                conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield Query(conn, self.postgres)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        conn = self.connect()
        try:
            if self.postgres:
                # Schema privado: não é o schema public exposto pela Data API do Supabase.
                conn.execute('CREATE SCHEMA IF NOT EXISTS arremate')
                conn.execute('REVOKE ALL ON SCHEMA arremate FROM PUBLIC')
                conn.execute('SET search_path TO arremate, public')
            else:
                conn.execute('PRAGMA journal_mode=WAL')
            sql = (ROOT / 'database/schema.sql').read_text(encoding='utf-8')
            for statement in sql.split(';'):
                if statement.strip():
                    conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

class Query:
    def __init__(self, conn, postgres):
        self.conn, self.postgres = conn, postgres

    def execute(self, sql, args=()):
        return self.conn.execute(sql.replace('?', '%s') if self.postgres else sql, args)

    def all(self, sql, args=()):
        return [dict(row) for row in self.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        row = self.execute(sql, args).fetchone()
        return dict(row) if row is not None else None
