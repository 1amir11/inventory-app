# seed_demo.py - creates data_demo\ with 14 days of clearly-labeled FAKE history.
#
# Covers: coffee + tea at 15 EGP, anise / hibiscus / mint sachets, packaging
# cup, potato plate, chicken, meat; mixed count units (carton, box, kg).
# The REAL first run always starts with an empty data\ folder + setup screen;
# this demo database is only for training and review.
#
# Usage:  python seed_demo.py [DEST_DIR]   (default: data_demo next to this file)
#
# Deterministic (fixed random seed) so every run produces the same numbers.
# Standard library only, Python 3.8 compatible.

import datetime
import json
import os
import random
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import calc  # noqa: E402
import db  # noqa: E402

DEMO_DIR_NAME = "data_demo"
DEMO_DAYS = 14
FIRST_DAY = datetime.date(2026, 9, 29)  # 14 days ending 2026-10-12
RNG = random.Random(42)

EGP = 100  # piasters per EGP


def _uid(conn, name):
    conn.execute("INSERT INTO users (name, created_at) VALUES (?, ?)",
                 (name, db.now_iso()))
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def _material(conn, uid, name, dept, base, units, cost_unit, cost_egp,
              cost_date="2026-09-01", is_cup=False):
    """units: [(unit_name, factor)]; first extra unit is the cost unit."""
    conn.execute(
        "INSERT INTO materials (name, department, base_unit, is_cup,"
        " created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, dept, base, 1 if is_cup else 0, uid, db.now_iso()))
    mid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        "INSERT INTO count_units (material_id, unit_name, factor_to_base,"
        " is_base_unit, created_by, created_at) VALUES (?, ?, 1, 1, ?, ?)",
        (mid, base, uid, db.now_iso()))
    unit_ids = {}
    for uname, factor in units:
        conn.execute(
            "INSERT INTO count_units (material_id, unit_name, factor_to_base,"
            " created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (mid, uname, factor, uid, db.now_iso()))
        unit_ids[uname] = conn.execute(
            "SELECT last_insert_rowid() AS id").fetchone()["id"]
    base_id = conn.execute(
        "SELECT id FROM count_units WHERE material_id = ? AND is_base_unit = 1",
        (mid,)).fetchone()["id"]
    unit_ids[base] = base_id
    conn.execute(
        "INSERT INTO material_costs (material_id, count_unit_id,"
        " price_piasters, effective_date, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (mid, unit_ids[cost_unit], int(cost_egp * EGP), cost_date, uid,
         db.now_iso()))
    return mid, unit_ids


def _product(conn, uid, name, dept, source, price_egp, price_date="2026-09-01",
             **extra):
    conn.execute(
        "INSERT INTO products (name, department, sold_source,"
        " source_material_id, recipe_qty_base, coffee_material_id, uses_cup,"
        " created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, dept, source, extra.get("source_material_id"),
         extra.get("recipe_qty_base"), extra.get("coffee_material_id"),
         1 if extra.get("uses_cup") else 0, uid, db.now_iso()))
    pid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        "INSERT INTO product_prices (product_id, price_piasters,"
        " effective_date, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (pid, int(price_egp * EGP), price_date, uid, db.now_iso()))
    return pid


def _recipe(conn, uid, pid, mid, qty_base, eff="2026-09-01"):
    conn.execute(
        "INSERT INTO recipe_lines (product_id, material_id, qty_base,"
        " effective_date, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (pid, mid, qty_base, eff, uid, db.now_iso()))


def build(dest_dir=None):
    dest = dest_dir or os.path.join(_APP_DIR, DEMO_DIR_NAME)
    if not os.path.isdir(dest):
        os.makedirs(dest)
    # Fresh demo every time: delete any previous demo DB (real data\ is never
    # touched - this script only ever writes inside data_demo\).
    # The demo DB is named exactly like the real one so the demo runs with:
    #     python server.py --data-dir data_demo
    demo_db = os.path.join(dest, "kitchen.db")
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(demo_db + suffix)
        except OSError:
            pass
    conn = db.connect(demo_db)
    db.apply_migrations(conn)

    with conn:
        db.set_setting(conn, "demo", "1", None)
        u1 = _uid(conn, "Ahmed")
        u2 = _uid(conn, "Mona")

        coffee_mid, coffee_u = _material(conn, u1, "coffee", "cafeteria", "g",
                                        [("bag", 250), ("carton", 2500)],
                                        "bag", 150.0)
        tea_mid, tea_u = _material(conn, u1, "tea", "cafeteria", "piece",
                                  [("box", 25), ("carton", 300)],
                                  "box", 75.0)
        anise_mid, anise_u = _material(conn, u1, "anise", "cafeteria", "piece",
                                      [("box", 25), ("carton", 300)],
                                      "box", 60.0)
        hib_mid, hib_u = _material(conn, u1, "hibiscus", "cafeteria", "piece",
                                  [("box", 25)], "box", 70.0)
        mint_mid, mint_u = _material(conn, u1, "mint", "cafeteria", "piece",
                                    [("box", 25)], "box", 65.0)
        cup_mid, cup_u = _material(conn, u1, "packaging cup", "cafeteria",
                                  "piece", [("pack", 50), ("carton", 1000)],
                                  "carton", 800.0, is_cup=True)
        potato_mid, potato_u = _material(conn, u1, "potato", "kitchen", "g",
                                        [("kg", 1000), ("sack", 10000)],
                                        "kg", 15.0)
        chicken_mid, chicken_u = _material(
            conn, u1, "chicken", "kitchen", "g", [("kg", 1000)], "kg", 120.0)
        meat_mid, meat_u = _material(conn, u1, "meat", "kitchen", "g",
                                    [("kg", 1000)], "kg", 220.0)

        tea_pid = _product(conn, u1, "tea", "cafeteria",
                           "derived_from_material", 15.0,
                           source_material_id=tea_mid, recipe_qty_base=1,
                           uses_cup=True)
        anise_pid = _product(conn, u1, "anise", "cafeteria",
                             "derived_from_material", 10.0,
                             source_material_id=anise_mid, recipe_qty_base=1,
                             uses_cup=True)
        hib_pid = _product(conn, u1, "hibiscus", "cafeteria",
                           "derived_from_material", 10.0,
                           source_material_id=hib_mid, recipe_qty_base=1,
                           uses_cup=True)
        mint_pid = _product(conn, u1, "mint", "cafeteria",
                            "derived_from_material", 10.0,
                            source_material_id=mint_mid, recipe_qty_base=1,
                            uses_cup=True)
        coffee_pid = _product(conn, u1, "coffee", "cafeteria",
                              "derived_remainder_of_cup", 15.0,
                              coffee_material_id=coffee_mid, uses_cup=True)
        potato_pid = _product(conn, u1, "potato plate", "kitchen", "manual",
                              25.0)
        chicken_pid = _product(conn, u1, "chicken", "kitchen", "manual", 60.0)
        meat_pid = _product(conn, u1, "meat", "kitchen", "manual", 80.0)

        for pid, smid in ((tea_pid, tea_mid), (anise_pid, anise_mid),
                          (hib_pid, hib_mid), (mint_pid, mint_mid)):
            _recipe(conn, u1, pid, smid, 1)
            _recipe(conn, u1, pid, cup_mid, 1)
        # Every hot drink includes 1 packaging cup - coffee included. The
        # coffee material itself has no recipe line: it is priced by the
        # measured yield, never double counted.
        _recipe(conn, u1, coffee_pid, cup_mid, 1)
        _recipe(conn, u1, potato_pid, potato_mid, 200)
        _recipe(conn, u1, chicken_pid, chicken_mid, 250)
        _recipe(conn, u1, meat_pid, meat_mid, 250)

    # Per-day simulation.
    balances = {coffee_mid: 5000, tea_mid: 600, anise_mid: 300, hib_mid: 200,
                mint_mid: 200, cup_mid: 2000, potato_mid: 30000,
                chicken_mid: 10000, meat_mid: 8000}
    # (restock lots, unit name) when the balance drops below `low_at`.
    restock = {coffee_mid: (2, "carton"), tea_mid: (1, "carton"),
               anise_mid: (2, "box"), hib_mid: (2, "box"),
               mint_mid: (2, "box"), cup_mid: (2, "carton"),
               potato_mid: (2, "sack"), chicken_mid: (10, "kg"),
               meat_mid: (10, "kg")}
    low_at = {coffee_mid: 3000, tea_mid: 300, anise_mid: 150,
              hib_mid: 100, mint_mid: 100, cup_mid: 1000,
              potato_mid: 15000, chicken_mid: 5000, meat_mid: 4000}
    mat_units = {coffee_mid: coffee_u, tea_mid: tea_u, anise_mid: anise_u,
                 hib_mid: hib_u, mint_mid: mint_u, cup_mid: cup_u,
                 potato_mid: potato_u, chicken_mid: chicken_u,
                 meat_mid: meat_u}

    for day_i in range(DEMO_DAYS):
        day = (FIRST_DAY + datetime.timedelta(days=day_i)).isoformat()
        uid = u1 if day_i % 2 == 0 else u2
        tea_cups = RNG.randint(25, 35)
        anise_cups = RNG.randint(8, 12)
        hib_cups = RNG.randint(5, 9)
        mint_cups = RNG.randint(4, 8)
        coffee_cups = RNG.randint(20, 40)
        total_cups = tea_cups + anise_cups + hib_cups + mint_cups + coffee_cups
        coffee_g = int(round(coffee_cups * RNG.uniform(9.5, 11.0)))
        potato_n = RNG.randint(8, 15)
        chicken_n = RNG.randint(5, 10)
        meat_n = RNG.randint(4, 8)
        want = {tea_mid: tea_cups, anise_mid: anise_cups, hib_mid: hib_cups,
                mint_mid: mint_cups, coffee_mid: coffee_g, cup_mid: total_cups,
                potato_mid: potato_n * 200 + RNG.randint(0, 300),
                chicken_mid: chicken_n * 250 + RNG.randint(0, 200),
                meat_mid: meat_n * 250 + RNG.randint(0, 200)}
        with conn:
            db.ensure_day(conn, day, uid)
            for mid, consumed_want in want.items():
                opening = balances[mid]
                # Receive stock when running low (every few days).
                received = 0
                if opening < low_at[mid]:
                    lots, uname = restock[mid]
                    factor = conn.execute(
                        "SELECT factor_to_base FROM count_units"
                        " WHERE id = ?", (mat_units[mid][uname],)).fetchone()[
                            "factor_to_base"]
                    received = lots * factor
                    conn.execute(
                        "INSERT INTO receipt_rows (business_date, material_id,"
                        " qty_entered, unit_id, qty_base, created_by,"
                        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (day, mid, float(lots), mat_units[mid][uname],
                         received, uid, db.now_iso()))
                closing = opening + received - consumed_want
                assert closing >= 0, (day, mid, closing)
                base_unit_id = conn.execute(
                    "SELECT id FROM count_units WHERE material_id = ?"
                    " AND is_base_unit = 1", (mid,)).fetchone()["id"]
                conn.execute(
                    "INSERT INTO stock_counts (business_date, material_id,"
                    " opening_base, opening_qty_entered, opening_unit_id,"
                    " closing_base, closing_qty_entered, closing_unit_id,"
                    " created_by, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (day, mid, opening, float(opening), base_unit_id,
                     closing, float(closing), base_unit_id, uid,
                     db.now_iso()))
                balances[mid] = closing
            for pid, qty in ((potato_pid, potato_n), (chicken_pid, chicken_n),
                             (meat_pid, meat_n)):
                conn.execute(
                    "INSERT INTO product_sales (business_date, product_id,"
                    " qty_sold, created_by, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (day, pid, qty, uid, db.now_iso()))
            conn.execute(
                "INSERT INTO coffee_checks (business_date, counted_cups,"
                " created_by, created_at) VALUES (?, ?, ?, ?)",
                (day, coffee_cups + RNG.choice([0, 0, 1, -1]), uid,
                 db.now_iso()))
            # Close with a stored snapshot (import here: routes need server's
            # context shape only for db_path; build_day_report takes conn).
            import routes_inventory  # noqa: E402
            report = routes_inventory.build_day_report(conn, day)
            conn.execute(
                "UPDATE business_days SET status = 'closed', closed_by = ?,"
                " closed_at = ?, snapshot_json = ? WHERE business_date = ?",
                (uid, db.now_iso(), json.dumps(report, ensure_ascii=False),
                 day))

    conn.commit()
    conn.close()
    with open(os.path.join(dest, "DEMO.txt"), "w", encoding="utf-8") as f:
        f.write("DEMO DATA - fake 14-day history for training/review, not real.\n"
                "Real first run starts with an empty data\\ folder.\n")
    return demo_db


def main():
    dest = sys.argv[1] if len(sys.argv) > 1 else None
    path = build(dest)
    print("Demo database: " + path)


if __name__ == "__main__":
    main()
