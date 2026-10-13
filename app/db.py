# db.py - database schema, migrations and storage helpers for the
# kitchen/cafeteria inventory + profit app.
#
# Rules honoured here:
#   - money is INTEGER piasters, quantities are INTEGER base units
#   - append-only after close: writes to a closed day raise DayClosedError,
#     except stock_adjustments rows (corrections with reason/user/timestamp)
#   - every write happens inside a transaction
#   - SQLite pragmas per connection: foreign_keys ON, synchronous FULL
#   - prices, costs and recipes are effective-dated; lookups pin to the
#     business date so past days never change when they are edited
#
# Standard library only (sqlite3), Python 3.8 compatible.

import os
import sqlite3
import time

import os
import sqlite3
import sys
import time

# Each module adds its own folder to sys.path first: the portable
# embeddable Python runs in ISOLATED mode (python38._pth), so a script's own
# directory is NOT automatically importable on the target PC.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

APP_DIR = _APP_DIR
DATA_DIR_NAME = "data"
DB_FILENAME = "kitchen.db"
BACKUP_DIR_NAME = "backups"
BACKUP_KEEP = 30


class DayClosedError(Exception):
    """Raised when a write targets a closed day (only adjustments allowed)."""


class ValidationError(Exception):
    """Raised for server-side validation failures (negatives, bad dates...)."""


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def default_data_dir():
    # type: () -> str
    return os.path.join(APP_DIR, DATA_DIR_NAME)


def default_db_path():
    # type: () -> str
    return os.path.join(default_data_dir(), DB_FILENAME)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect(db_path=None):
    # type: (str) -> sqlite3.Connection
    """Open the DB with integrity pragmas. Creates data/ if missing."""
    path = db_path if db_path is not None else default_db_path()
    if path != ":memory:":
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = FULL")
    return conn


def pragmas_ok(conn):
    # type: (sqlite3.Connection) -> bool
    """True when this connection enforces the required pragmas."""
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    return fk == 1 and sync == 2  # 2 == FULL


# ---------------------------------------------------------------------------
# Migrations (numbered, applied once, never edit a released step)
# ---------------------------------------------------------------------------

MIGRATIONS = (
    (1, "inventory phase 1 tables", (
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT NOT NULL
                CHECK (department IN ('kitchen', 'cafeteria')),
            base_unit TEXT NOT NULL
                CHECK (base_unit IN ('g', 'ml', 'piece')),
            is_cup INTEGER NOT NULL DEFAULT 0
                CHECK (is_cup IN (0, 1)),
            active INTEGER NOT NULL DEFAULT 1
                CHECK (active IN (0, 1)),
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE count_units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL REFERENCES materials(id),
            unit_name TEXT NOT NULL,
            factor_to_base INTEGER NOT NULL
                CHECK (typeof(factor_to_base) = 'integer'
                       AND factor_to_base > 0),
            is_base_unit INTEGER NOT NULL DEFAULT 0
                CHECK (is_base_unit IN (0, 1)),
            active INTEGER NOT NULL DEFAULT 1
                CHECK (active IN (0, 1)),
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL,
            UNIQUE (material_id, unit_name)
        )
        """,
        """
        CREATE TABLE material_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL REFERENCES materials(id),
            count_unit_id INTEGER NOT NULL REFERENCES count_units(id),
            price_piasters INTEGER NOT NULL
                CHECK (typeof(price_piasters) = 'integer'
                       AND price_piasters >= 0),
            effective_date TEXT NOT NULL,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT NOT NULL
                CHECK (department IN ('kitchen', 'cafeteria')),
            sold_source TEXT NOT NULL
                CHECK (sold_source IN ('derived_from_material',
                                       'derived_remainder_of_cup',
                                       'manual')),
            source_material_id INTEGER REFERENCES materials(id),
            recipe_qty_base INTEGER
                CHECK (recipe_qty_base IS NULL
                       OR (typeof(recipe_qty_base) = 'integer'
                           AND recipe_qty_base > 0)),
            coffee_material_id INTEGER REFERENCES materials(id),
            uses_cup INTEGER NOT NULL DEFAULT 0
                CHECK (uses_cup IN (0, 1)),
            active INTEGER NOT NULL DEFAULT 1
                CHECK (active IN (0, 1)),
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE product_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            price_piasters INTEGER NOT NULL
                CHECK (typeof(price_piasters) = 'integer'
                       AND price_piasters >= 0),
            effective_date TEXT NOT NULL,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE recipe_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            material_id INTEGER NOT NULL REFERENCES materials(id),
            qty_base INTEGER NOT NULL
                CHECK (typeof(qty_base) = 'integer' AND qty_base >= 0),
            effective_date TEXT NOT NULL,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE business_days (
            business_date TEXT PRIMARY KEY
                CHECK (business_date LIKE '____-__-__'),
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'closed')),
            closed_by INTEGER REFERENCES users(id),
            closed_at TEXT,
            snapshot_json TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE stock_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_date TEXT NOT NULL REFERENCES business_days(business_date),
            material_id INTEGER NOT NULL REFERENCES materials(id),
            opening_base INTEGER NOT NULL
                CHECK (typeof(opening_base) = 'integer' AND opening_base >= 0),
            opening_qty_entered REAL NOT NULL,
            opening_unit_id INTEGER NOT NULL REFERENCES count_units(id),
            closing_base INTEGER
                CHECK (closing_base IS NULL
                       OR (typeof(closing_base) = 'integer'
                           AND closing_base >= 0)),
            closing_qty_entered REAL,
            closing_unit_id INTEGER REFERENCES count_units(id),
            opening_reason TEXT,
            closing_reason TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL,
            UNIQUE (business_date, material_id)
        )
        """,
        """
        CREATE TABLE receipt_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_date TEXT NOT NULL REFERENCES business_days(business_date),
            material_id INTEGER NOT NULL REFERENCES materials(id),
            qty_entered REAL NOT NULL CHECK (qty_entered >= 0),
            unit_id INTEGER NOT NULL REFERENCES count_units(id),
            qty_base INTEGER NOT NULL
                CHECK (typeof(qty_base) = 'integer' AND qty_base >= 0),
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE stock_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_date TEXT NOT NULL REFERENCES business_days(business_date),
            material_id INTEGER NOT NULL REFERENCES materials(id),
            delta_base INTEGER NOT NULL
                CHECK (typeof(delta_base) = 'integer'),
            reason TEXT NOT NULL,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE product_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_date TEXT NOT NULL REFERENCES business_days(business_date),
            product_id INTEGER NOT NULL REFERENCES products(id),
            qty_sold INTEGER NOT NULL
                CHECK (typeof(qty_sold) = 'integer' AND qty_sold >= 0),
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL,
            UNIQUE (business_date, product_id)
        )
        """,
        """
        CREATE TABLE coffee_checks (
            business_date TEXT PRIMARY KEY REFERENCES business_days(business_date),
            counted_cups INTEGER
                CHECK (counted_cups IS NULL
                       OR (typeof(counted_cups) = 'integer'
                           AND counted_cups >= 0)),
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        )
        """,
        # Small key/value settings (initial coffee estimates...). Seeded with
        # defaults on first use; editable from the UI without a migration.
        """
        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_by INTEGER REFERENCES users(id),
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            entity_id INTEGER,
            business_date TEXT,
            before_json TEXT,
            after_json TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_costs_material ON material_costs(material_id, effective_date)",
        "CREATE INDEX idx_prices_product ON product_prices(product_id, effective_date)",
        "CREATE INDEX idx_recipe_product ON recipe_lines(product_id, effective_date)",
        "CREATE INDEX idx_counts_day ON stock_counts(business_date)",
        "CREATE INDEX idx_receipts_day ON receipt_rows(business_date)",
        "CREATE INDEX idx_sales_day ON product_sales(business_date)",
        "CREATE INDEX idx_audit_entity ON audit_log(entity, entity_id)",
    )),
)

LATEST_VERSION = MIGRATIONS[-1][0]


def _ensure_schema_version(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """)


def schema_version(conn):
    _ensure_schema_version(conn)
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    value = row["v"] if row is not None else None
    return int(value) if value is not None else 0


def apply_migrations(conn, up_to=None):
    _ensure_schema_version(conn)
    conn.commit()
    current = schema_version(conn)
    applied = []
    previous_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        for number, description, statements in MIGRATIONS:
            if number <= current:
                continue
            if up_to is not None and number > up_to:
                break
            conn.execute("BEGIN")
            try:
                for statement in statements:
                    if callable(statement):
                        statement(conn)
                    else:
                        conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_version (version, description, applied_at)"
                    " VALUES (?, ?, datetime('now'))",
                    (number, description))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            applied.append(number)
    finally:
        conn.isolation_level = previous_isolation
    return applied


def table_names(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    return [row["name"] for row in rows]


def init_db(db_path=None):
    conn = connect(db_path)
    apply_migrations(conn)
    return conn


# ---------------------------------------------------------------------------
# Timestamps (UTC ISO; the business date itself is always explicit input)
# ---------------------------------------------------------------------------

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Day + closed-day guard
# ---------------------------------------------------------------------------

def day_status(conn, business_date):
    row = conn.execute(
        "SELECT status FROM business_days WHERE business_date = ?",
        (business_date,)).fetchone()
    return row["status"] if row is not None else None


def ensure_day(conn, business_date, user_id=None):
    """Create the business day row (open) if missing. Never touches closed."""
    if day_status(conn, business_date) is None:
        conn.execute(
            "INSERT INTO business_days (business_date, status, created_at)"
            " VALUES (?, 'open', ?)",
            (business_date, now_iso()))


def require_open(conn, business_date):
    """Raise DayClosedError when the day is closed."""
    if day_status(conn, business_date) == "closed":
        raise DayClosedError("day %s is closed" % business_date)


# ---------------------------------------------------------------------------
# Reads used by the API (opening defaults, totals, averages, lookups)
# ---------------------------------------------------------------------------

def effective_closing(conn, material_id, business_date):
    """Closing of the latest day strictly before business_date, plus any
    adjustments booked to that day (corrections must carry forward)."""
    row = conn.execute(
        "SELECT c.closing_base AS closing, c.business_date AS day"
        " FROM stock_counts c WHERE c.material_id = ?"
        " AND c.business_date < ? AND c.closing_base IS NOT NULL"
        " ORDER BY c.business_date DESC LIMIT 1",
        (material_id, business_date)).fetchone()
    if row is None:
        return 0
    adj = conn.execute(
        "SELECT COALESCE(SUM(delta_base), 0) AS total FROM stock_adjustments"
        " WHERE material_id = ? AND business_date = ?",
        (material_id, row["day"])).fetchone()
    return (row["closing"] or 0) + (adj["total"] or 0)


def received_total(conn, material_id, business_date):
    row = conn.execute(
        "SELECT COALESCE(SUM(qty_base), 0) AS total FROM receipt_rows"
        " WHERE material_id = ? AND business_date = ?",
        (material_id, business_date)).fetchone()
    return row["total"] or 0


def adjustments_total(conn, material_id, business_date):
    row = conn.execute(
        "SELECT COALESCE(SUM(delta_base), 0) AS total FROM stock_adjustments"
        " WHERE material_id = ? AND business_date = ?",
        (material_id, business_date)).fetchone()
    return row["total"] or 0


def average14(conn, material_id, business_date):
    """Mean of up to 14 most recent non-null closings before the given day."""
    rows = conn.execute(
        "SELECT closing_base FROM stock_counts WHERE material_id = ?"
        " AND business_date < ? AND closing_base IS NOT NULL"
        " ORDER BY business_date DESC LIMIT 14",
        (material_id, business_date)).fetchall()
    if not rows:
        return 0.0
    return sum(r["closing_base"] for r in rows) / float(len(rows))


def costs_as_of(conn, business_date):
    """{material_id: (price_piasters, factor)} effective on the given day."""
    out = {}
    rows = conn.execute(
        "SELECT mc.material_id AS mid, mc.price_piasters AS price,"
        " u.factor_to_base AS factor, mc.effective_date AS eff"
        " FROM material_costs mc JOIN count_units u"
        " ON u.id = mc.count_unit_id"
        " WHERE mc.effective_date <= ?"
        " ORDER BY mc.material_id, mc.effective_date",
        (business_date,)).fetchall()
    for row in rows:
        out[row["mid"]] = (row["price"], row["factor"])
    return out


def prices_as_of(conn, business_date):
    """{product_id: price_piasters} effective on the given day."""
    out = {}
    rows = conn.execute(
        "SELECT product_id AS pid, price_piasters AS price FROM product_prices"
        " WHERE effective_date <= ? ORDER BY product_id, effective_date",
        (business_date,)).fetchall()
    for row in rows:
        out[row["pid"]] = row["price"]
    return out


def recipes_as_of(conn, business_date):
    """{product_id: [{material_id, qty_base}]} effective on the given day.

    Per (product, material) the latest line on/before the day wins; a qty of
    0 removes the material from the recipe."""
    latest = {}
    rows = conn.execute(
        "SELECT product_id AS pid, material_id AS mid, qty_base AS qty,"
        " effective_date AS eff FROM recipe_lines WHERE effective_date <= ?"
        " ORDER BY product_id, material_id, effective_date",
        (business_date,)).fetchall()
    for row in rows:
        latest[(row["pid"], row["mid"])] = row["qty"]
    out = {}
    for (pid, mid), qty in latest.items():
        if qty > 0:
            out.setdefault(pid, []).append(
                {"material_id": mid, "qty_base": qty})
    return out


def list_materials(conn, active_only=True):
    sql = "SELECT * FROM materials"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY id"
    return conn.execute(sql).fetchall()


def list_products(conn, active_only=True):
    sql = "SELECT * FROM products"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY id"
    return conn.execute(sql).fetchall()


def units_for(conn, material_id):
    return conn.execute(
        "SELECT * FROM count_units WHERE material_id = ? AND active = 1"
        " ORDER BY is_base_unit DESC, id",
        (material_id,)).fetchall()


# ---------------------------------------------------------------------------
# Small settings (no migration needed to change an estimate)
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "initial_gpc": "10.0",       # fallback grams-per-cup before any history
    "coffee_bag_grams": "250",   # bag size used for the cups-per-bag display
    "yield_window_days": "30",   # default yield period
}


def get_setting(conn, key):
    # type: (sqlite3.Connection, str) -> str
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?",
                       (key,)).fetchone()
    if row is not None:
        return row["value"]
    return DEFAULT_SETTINGS.get(key, "")


def set_setting(conn, key, value, user_id=None):
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value, updated_by, updated_at)"
        " VALUES (?, ?, ?, ?)", (key, value, user_id, now_iso()))


# ---------------------------------------------------------------------------
# Backups (sqlite3 backup API; keep last 30)
# ---------------------------------------------------------------------------

def backup_db(db_path=None, backup_dir=None, keep=BACKUP_KEEP):
    """Copy the live DB with the online backup API. Returns the new file path.

    Works while the app runs; never touches data/ contents besides adding a
    timestamped copy under data/backups/.
    """
    src = db_path if db_path is not None else default_db_path()
    dest_dir = backup_dir
    if dest_dir is None:
        base = os.path.dirname(os.path.abspath(src))
        dest_dir = os.path.join(base, BACKUP_DIR_NAME)
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    dest = os.path.join(dest_dir, "kitchen_%s.db" % stamp)
    n = 0
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(dest_dir, "kitchen_%s_%d.db" % (stamp, n))
    src_conn = sqlite3.connect(src)
    try:
        dst_conn = sqlite3.connect(dest)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    _prune_backups(dest_dir, keep)
    return dest


def _prune_backups(dest_dir, keep):
    try:
        names = sorted(f for f in os.listdir(dest_dir)
                       if f.startswith("kitchen_") and f.endswith(".db"))
    except OSError:
        return
    for old in names[:-keep] if len(names) > keep else []:
        try:
            os.remove(os.path.join(dest_dir, old))
        except OSError:
            pass


def main():
    path = default_db_path()
    print("Database file : " + path)
    print("SQLite        : " + sqlite3.sqlite_version)
    conn = init_db(path)
    try:
        print("Schema version: %d" % schema_version(conn))
        print("Tables        : " + ", ".join(table_names(conn)))
        print("Pragmas OK    : %s" % pragmas_ok(conn))
    finally:
        conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
