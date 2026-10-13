# test_db_rules.py - unit tests for app/db.py: schema, closed-day
# immutability, carry-forward, effective-dated lookups, backups.
#
# Run from the repository root:  python -m unittest discover -s tests -v
# Standard library only (unittest), Python 3.8 compatible.

import os
import sqlite3
import sys
import tempfile
import unittest

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_DIR = os.path.join(_ROOT_DIR, "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import db  # noqa: E402


def fresh_db():
    conn = db.connect(":memory:")
    db.apply_migrations(conn)
    return conn


def add_user(conn, name):
    conn.execute("INSERT INTO users (name, created_at) VALUES (?, ?)",
                 (name, db.now_iso()))
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def add_material(conn, uid, name="tea", dept="cafeteria", base="piece"):
    conn.execute(
        "INSERT INTO materials (name, department, base_unit, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?)", (name, dept, base, uid, db.now_iso()))
    mid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        "INSERT INTO count_units (material_id, unit_name, factor_to_base,"
        " is_base_unit, created_by, created_at)"
        " VALUES (?, ?, 1, 1, ?, ?)", (mid, base, uid, db.now_iso()))
    return mid


class TestSchema(unittest.TestCase):

    def test_tables_exist(self):
        conn = fresh_db()
        try:
            names = db.table_names(conn)
            for expected in ("users", "materials", "count_units",
                             "material_costs", "products", "product_prices",
                             "recipe_lines", "business_days", "stock_counts",
                             "receipt_rows", "stock_adjustments",
                             "product_sales", "coffee_checks", "audit_log",
                             "app_settings", "schema_version"):
                self.assertIn(expected, names)
            self.assertEqual(db.schema_version(conn), db.LATEST_VERSION)
        finally:
            conn.close()

    def test_pragmas(self):
        conn = fresh_db()
        try:
            self.assertTrue(db.pragmas_ok(conn))
        finally:
            conn.close()

    def test_foreign_keys_enforced(self):
        conn = fresh_db()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO count_units (material_id, unit_name,"
                    " factor_to_base, created_at) VALUES (999, 'x', 1, 't')")
        finally:
            conn.close()

    def test_money_rejects_float(self):
        conn = fresh_db()
        try:
            uid = add_user(conn, "u1")
            mid = add_material(conn, uid)
            unit = conn.execute(
                "SELECT id FROM count_units WHERE material_id = ?",
                (mid,)).fetchone()["id"]
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO material_costs (material_id, count_unit_id,"
                    " price_piasters, effective_date, created_at)"
                    " VALUES (?, ?, 10.5, '2026-01-01', 't')", (mid, unit))
        finally:
            conn.close()


class TestClosedDayImmutability(unittest.TestCase):

    def setUp(self):
        self.conn = fresh_db()
        self.uid = add_user(self.conn, "checker")
        self.mid = add_material(self.conn, self.uid)
        db.ensure_day(self.conn, "2026-10-01", self.uid)
        self.conn.execute(
            "INSERT INTO stock_counts (business_date, material_id,"
            " opening_base, opening_qty_entered, opening_unit_id,"
            " closing_base, closing_qty_entered, closing_unit_id,"
            " created_by, created_at)"
            " VALUES ('2026-10-01', ?, 10, 10.0, 1, 4, 4.0, 1, ?, ?)",
            (self.mid, self.uid, db.now_iso()))
        self.conn.execute(
            "UPDATE business_days SET status = 'closed' WHERE business_date = ?",
            ("2026-10-01",))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_closed_day_detected(self):
        self.assertEqual(db.day_status(self.conn, "2026-10-01"), "closed")

    def test_require_open_raises(self):
        with self.assertRaises(db.DayClosedError):
            db.require_open(self.conn, "2026-10-01")

    def test_open_day_passes(self):
        db.ensure_day(self.conn, "2026-10-02", self.uid)
        db.require_open(self.conn, "2026-10-02")  # must not raise

    def test_adjustment_allowed_on_closed_day(self):
        # Corrections are new adjustment rows, never UPDATE/DELETE.
        self.conn.execute(
            "INSERT INTO stock_adjustments (business_date, material_id,"
            " delta_base, reason, created_by, created_at)"
            " VALUES ('2026-10-01', ?, -2, 'recount', ?, ?)",
            (self.mid, self.uid, db.now_iso()))
        self.conn.commit()
        self.assertEqual(db.adjustments_total(self.conn, self.mid,
                                             "2026-10-01"), -2)
        # The original row is untouched.
        row = self.conn.execute(
            "SELECT closing_base FROM stock_counts WHERE business_date = ?",
            ("2026-10-01",)).fetchone()
        self.assertEqual(row["closing_base"], 4)


class TestCarryForward(unittest.TestCase):

    def test_opening_defaults_to_prev_closing(self):
        conn = fresh_db()
        try:
            uid = add_user(conn, "u")
            mid = add_material(conn, uid)
            db.ensure_day(conn, "2026-10-01", uid)
            unit = conn.execute(
                "SELECT id FROM count_units WHERE material_id = ?",
                (mid,)).fetchone()["id"]
            conn.execute(
                "INSERT INTO stock_counts (business_date, material_id,"
                " opening_base, opening_qty_entered, opening_unit_id,"
                " closing_base, created_by, created_at)"
                " VALUES ('2026-10-01', ?, 10, 10.0, ?, 6, ?, ?)",
                (mid, unit, uid, db.now_iso()))
            conn.commit()
            self.assertEqual(db.effective_closing(conn, mid, "2026-10-02"), 6)
            # No history -> 0.
            self.assertEqual(db.effective_closing(conn, mid, "2026-10-01"), 0)
        finally:
            conn.close()

    def test_adjustment_carries_forward(self):
        conn = fresh_db()
        try:
            uid = add_user(conn, "u")
            mid = add_material(conn, uid)
            db.ensure_day(conn, "2026-10-01", uid)
            unit = conn.execute(
                "SELECT id FROM count_units WHERE material_id = ?",
                (mid,)).fetchone()["id"]
            conn.execute(
                "INSERT INTO stock_counts (business_date, material_id,"
                " opening_base, opening_qty_entered, opening_unit_id,"
                " closing_base, created_by, created_at)"
                " VALUES ('2026-10-01', ?, 10, 10.0, ?, 6, ?, ?)",
                (mid, unit, uid, db.now_iso()))
            conn.execute(
                "INSERT INTO stock_adjustments (business_date, material_id,"
                " delta_base, reason, created_by, created_at)"
                " VALUES ('2026-10-01', ?, 2, 'found box', ?, ?)",
                (mid, uid, db.now_iso()))
            conn.commit()
            self.assertEqual(db.effective_closing(conn, mid, "2026-10-02"), 8)
        finally:
            conn.close()


class TestEffectiveLookups(unittest.TestCase):

    def test_costs_prices_recipes_frozen(self):
        conn = fresh_db()
        try:
            uid = add_user(conn, "u")
            mid = add_material(conn, uid, name="coffee", base="g")
            unit = conn.execute(
                "SELECT id FROM count_units WHERE material_id = ?",
                (mid,)).fetchone()["id"]
            conn.execute(
                "INSERT INTO material_costs (material_id, count_unit_id,"
                " price_piasters, effective_date, created_at)"
                " VALUES (?, ?, 3000, '2026-01-01', 't')", (mid, unit))
            conn.execute(
                "INSERT INTO material_costs (material_id, count_unit_id,"
                " price_piasters, effective_date, created_at)"
                " VALUES (?, ?, 4000, '2026-02-01', 't')", (mid, unit))
            conn.execute(
                "INSERT INTO products (name, department, sold_source,"
                " created_at) VALUES ('coffee', 'cafeteria',"
                " 'derived_remainder_of_cup', 't')")
            pid = conn.execute(
                "SELECT last_insert_rowid() AS id").fetchone()["id"]
            conn.execute(
                "INSERT INTO product_prices (product_id, price_piasters,"
                " effective_date, created_at)"
                " VALUES (?, 1500, '2026-01-01', 't')", (pid,))
            conn.execute(
                "INSERT INTO recipe_lines (product_id, material_id, qty_base,"
                " effective_date, created_at) VALUES (?, ?, 10,"
                " '2026-01-01', 't')", (pid, mid))
            conn.commit()
            jan = db.costs_as_of(conn, "2026-01-15")
            feb = db.costs_as_of(conn, "2026-02-15")
            self.assertEqual(jan[mid], (3000, 1))
            self.assertEqual(feb[mid], (4000, 1))
            self.assertEqual(db.prices_as_of(conn, "2026-06-01")[pid], 1500)
            self.assertEqual(db.recipes_as_of(conn, "2026-06-01")[pid],
                             [{"material_id": mid, "qty_base": 10}])
            # Removing an ingredient (qty 0) drops it from later lookups
            # but keeps old days intact.
            conn.execute(
                "INSERT INTO recipe_lines (product_id, material_id, qty_base,"
                " effective_date, created_at) VALUES (?, ?, 0,"
                " '2026-03-01', 't')", (pid, mid))
            conn.commit()
            self.assertEqual(db.recipes_as_of(conn, "2026-01-15")[pid],
                             [{"material_id": mid, "qty_base": 10}])
            self.assertNotIn(pid, db.recipes_as_of(conn, "2026-04-01"))
        finally:
            conn.close()


class TestBackups(unittest.TestCase):

    def test_backup_and_prune(self):
        tmp = tempfile.mkdtemp(prefix="kitchen_bak_")
        try:
            src = os.path.join(tmp, "kitchen.db")
            conn = db.connect(src)
            db.apply_migrations(conn)
            conn.close()
            dest_dir = os.path.join(tmp, "backups")
            first = db.backup_db(src, dest_dir, keep=3)
            self.assertTrue(os.path.isfile(first))
            for _i in range(4):
                db.backup_db(src, dest_dir, keep=3)
            names = sorted(f for f in os.listdir(dest_dir)
                           if f.endswith(".db"))
            self.assertEqual(len(names), 3)
            # The backup is a real database with our schema.
            probe = sqlite3.connect(os.path.join(dest_dir, names[0]))
            try:
                tables = [r[0] for r in probe.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                self.assertIn("materials", tables)
            finally:
                probe.close()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
