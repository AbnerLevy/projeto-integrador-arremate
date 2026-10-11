-- SQL compatível com SQLite e PostgreSQL. Aplicado por python app.py init.
CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 0, next_code INTEGER NOT NULL DEFAULT 1);
INSERT INTO meta(id) VALUES(1) ON CONFLICT(id) DO NOTHING;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, username TEXT NOT NULL UNIQUE,
 specialty TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('manager','worker')),
 password_hash TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_limits (key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, reset_at BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT NOT NULL, price_cents INTEGER NOT NULL CHECK(price_cents>=0));
CREATE TABLE IF NOT EXISTS stages (id TEXT PRIMARY KEY, name TEXT NOT NULL, sector TEXT NOT NULL, position INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS batches (
 id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, product TEXT NOT NULL, client TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity>0), price_cents INTEGER NOT NULL CHECK(price_cents>=0),
 color TEXT NOT NULL, sizes TEXT NOT NULL, due_date TEXT NOT NULL, notes TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id), position INTEGER NOT NULL,
 name TEXT NOT NULL, sector TEXT NOT NULL, assignee_id TEXT NOT NULL REFERENCES users(id),
 planned_date TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('waiting','ready','active','done','cancelled')),
 incoming INTEGER NOT NULL CHECK(incoming>=0), outgoing INTEGER NOT NULL CHECK(outgoing>=0 AND outgoing<=incoming),
 started_at TEXT, completed_at TEXT, UNIQUE(batch_id,position)
);
CREATE TABLE IF NOT EXISTS losses (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), batch_id TEXT NOT NULL REFERENCES batches(id),
 actor_id TEXT NOT NULL REFERENCES users(id), quantity INTEGER NOT NULL CHECK(quantity>=0), reason TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notices (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), batch_id TEXT NOT NULL REFERENCES batches(id),
 message TEXT NOT NULL, seen INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, actor_id TEXT NOT NULL REFERENCES users(id), payload_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tasks_batch ON tasks(batch_id,position);
CREATE INDEX IF NOT EXISTS idx_notices_user ON notices(user_id,seen);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires);
