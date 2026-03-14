SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT UNIQUE NOT NULL,
    email        TEXT UNIQUE NOT NULL,
    password     TEXT NOT NULL,
    balance      REAL DEFAULT 0,
    role         TEXT DEFAULT 'user',
    api_key      TEXT UNIQUE,
    total_spent  REAL DEFAULT 0,
    total_orders INTEGER DEFAULT 0,
    ref_code     TEXT UNIQUE,
    referred_by  INTEGER,
    ref_earnings REAL DEFAULT 0,
    is_active    INTEGER DEFAULT 1,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    icon       TEXT DEFAULT 'fas fa-star',
    sort_order INTEGER DEFAULT 0,
    is_active  INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS services (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id     INTEGER NOT NULL,
    provider_id     INTEGER,
    name            TEXT NOT NULL,
    description     TEXT,
    type            TEXT DEFAULT 'Default',
    platform        TEXT,
    price_per_1000  REAL NOT NULL,
    min_order       INTEGER DEFAULT 10,
    max_order       INTEGER DEFAULT 100000,
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    service_id      INTEGER NOT NULL,
    provider_order_id TEXT,
    link            TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    price           REAL NOT NULL,
    start_count     INTEGER DEFAULT 0,
    remains         INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'Pending',
    note            TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(user_id)    REFERENCES users(id),
    FOREIGN KEY(service_id) REFERENCES services(id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    type        TEXT NOT NULL,
    amount      REAL NOT NULL,
    description TEXT,
    ref_id      TEXT,
    status      TEXT DEFAULT 'completed',
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS deposits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL NOT NULL,
    method      TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    external_id TEXT,
    tx_hash     TEXT,
    raw_data    TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    confirmed_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tickets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    subject    TEXT NOT NULL,
    status     TEXT DEFAULT 'open',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    message    TEXT NOT NULL,
    is_admin   INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(ticket_id) REFERENCES tickets(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

SEED = """
INSERT OR IGNORE INTO categories (name, icon, sort_order) VALUES
    ('Instagram',  'fab fa-instagram', 1),
    ('YouTube',    'fab fa-youtube',   2),
    ('TikTok',     'fab fa-tiktok',    3),
    ('Telegram',   'fab fa-telegram',  4),
    ('Twitter/X',  'fab fa-twitter',   5),
    ('Facebook',   'fab fa-facebook',  6);

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('site_name',      'SMMPanel.uz'),
    ('site_desc',      'O''zbekistondagi eng arzon SMM panel'),
    ('min_deposit',    '5000'),
    ('currency',       'UZS'),
    ('maintenance',    '0'),
    ('reg_bonus',      '0');
"""