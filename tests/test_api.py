# test_api.py - end-to-end tests of the JSON API on a live local server.
#
# Binds 127.0.0.1 on an ephemeral port with a temp data dir; exercises the
# full day flow: setup -> materials -> products -> counts -> close, plus
# closed-day immutability, reason flows, reconciliation and CSV export.
#
# Run from the repository root:  python -m unittest discover -s tests -v
# Standard library only (unittest + urllib), Python 3.8 compatible.

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import urllib.request
import urllib.error

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_DIR = os.path.join(_ROOT_DIR, "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import server  # noqa: E402


class ApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kitchen_api_")
        cls.db_path = os.path.join(cls.tmp, "kitchen.db")
        cls.httpd, cls.context = server.create_server("127.0.0.1", 0,
                                                     db_path=cls.db_path)
        import threading
        cls.thread = threading.Thread(target=cls.httpd.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- helpers ---------------------------------------------------------
    def call(self, method, path, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except ValueError:
                body = {}
            finally:
                exc.close()
            return exc.code, body

    def get(self, path):
        req = urllib.request.Request(self.base + path, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                ctype = resp.headers.get("Content-Type") or ""
                if "json" in ctype:
                    return resp.status, json.loads(raw.decode("utf-8"))
                return resp.status, raw.decode("utf-8-sig")
        except urllib.error.HTTPError as exc:
            return exc.code, {}

    # -- the flow ---------------------------------------------------------
    def test_01_full_day_flow(self):
        status, body = self.get("/api/session")
        self.assertEqual(status, 200)
        # Launcher probe markers must be present on this PUBLIC endpoint.
        self.assertIn("authenticated", body)
        self.assertIn("setup_required", body)
        self.assertTrue(body["setup_required"])

        status, body = self.call("POST", "/api/users", {"name": "Ahmed"})
        self.assertEqual(status, 200)
        uid = body["id"]
        status, body = self.call("POST", "/api/users",
                                 {"name": "Mona", "user_id": uid})
        self.assertEqual(status, 200)

        def mat(name, dept, base, extra_units=()):
            st, bd = self.call("POST", "/api/materials",
                               {"name": name, "department": dept,
                                "base_unit": base, "user_id": uid,
                                "units": [{"unit_name": u, "factor_to_base": f}
                                          for u, f in extra_units]})
            self.assertEqual(st, 200, (name, bd))
            return bd["id"]

        tea = mat("tea", "cafeteria", "piece", [("box", 25)])
        cup = mat("cup", "cafeteria", "piece", [("pack", 50)])
        cof = mat("coffee", "cafeteria", "g", [("bag", 250)])
        pot = mat("potato", "kitchen", "g", [("kg", 1000)])
        # Mark the cup material as the packaging cup.
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE materials SET is_cup = 1 WHERE id = ?", (cup,))
        conn.commit()
        conn.close()

        st, mats = self.get("/api/materials")
        units = {m["name"]: {u["unit_name"]: u["id"] for u in m["units"]}
                 for m in mats["materials"]}

        def cost(mid, uname, price, eff):
            st, bd = self.call("POST", "/api/costs",
                               {"material_id": mid, "unit_id": units[
                                   {tea: "tea", cup: "cup", cof: "coffee",
                                    pot: "potato"}[mid]][uname],
                                "price_piasters": price,
                                "effective_date": eff, "user_id": uid})
            self.assertEqual(st, 200, bd)

        cost(tea, "box", 7500, "2026-01-01")     # 300 piaster/sachet
        cost(cup, "pack", 4000, "2026-01-01")    # 80 piaster/cup
        cost(cof, "bag", 15000, "2026-01-01")    # 60 piaster/g
        cost(pot, "kg", 1500, "2026-01-01")      # 1.5 piaster/g

        def prod(name, dept, source, price, **kw):
            payload = {"name": name, "department": dept,
                       "sold_source": source, "user_id": uid,
                       "first_price": {"price_piasters": price,
                                       "effective_date": "2026-01-01"}}
            payload.update(kw)
            st, bd = self.call("POST", "/api/products", payload)
            self.assertEqual(st, 200, (name, bd))
            return bd["id"]

        tea_p = prod("tea", "cafeteria", "derived_from_material", 1500,
                     source_material_id=tea, recipe_qty_entered=1.0,
                     recipe_unit_id=units["tea"]["piece"], uses_cup=True)
        cof_p = prod("coffee", "cafeteria", "derived_remainder_of_cup", 1500,
                     coffee_material_id=cof, uses_cup=True)
        pot_p = prod("potato plate", "kitchen", "manual", 2500)
        st, bd = self.call("POST", "/api/recipe",
                           {"product_id": pot_p, "material_id": pot,
                            "qty_entered": 0.2, "unit_id": units["potato"]["kg"],
                            "effective_date": "2026-01-01", "user_id": uid})
        self.assertEqual(st, 200)
        self.assertEqual(bd["qty_base"], 200)  # 0.2 kg -> 200 g

        day = "2026-10-01"

        def count(mid, field, qty, uname, reason=None):
            names = {tea: "tea", cup: "cup", cof: "coffee", pot: "potato"}
            payload = {"date": day, "material_id": mid, "field": field,
                       "qty_entered": qty,
                       "unit_id": units[names[mid]][uname], "user_id": uid}
            if reason:
                payload["reason"] = reason
            return self.call("POST", "/api/day/count", payload)

        # Opening defaults to 0 (no history) - no reason needed.
        for mid, uname in ((tea, "piece"), (cup, "piece"), (cof, "g"),
                           (pot, "g")):
            st, bd = count(mid, "opening", 0, uname)
            self.assertEqual(st, 200, bd)
        # Receive 1 box of tea (25 sachets).
        st, bd = self.call("POST", "/api/day/receipt",
                           {"date": day, "material_id": tea,
                            "qty_entered": 1.0,
                            "unit_id": units["tea"]["box"], "user_id": uid})
        self.assertEqual(st, 200)
        self.assertEqual(bd["qty_base"], 25)
        # Closing tea at 5 -> consumed 20 -> 20 cups.
        st, bd = count(tea, "closing", 5, "piece")
        self.assertEqual(st, 200)
        # Cups: receive 100 pieces, close at 70 -> 30 consumed.
        st, bd = self.call("POST", "/api/day/receipt",
                           {"date": day, "material_id": cup,
                            "qty_entered": 100.0,
                            "unit_id": units["cup"]["piece"], "user_id": uid})
        self.assertEqual(st, 200)
        # Opening cup was 0 and we received 100: closing 70 is fine.
        st, bd = count(cup, "closing", 70, "piece")
        self.assertEqual(st, 200)
        # Coffee: receive 1 bag, close so 100 g consumed.
        st, bd = self.call("POST", "/api/day/receipt",
                           {"date": day, "material_id": cof,
                            "qty_entered": 1.0,
                            "unit_id": units["coffee"]["bag"], "user_id": uid})
        self.assertEqual(st, 200)
        st, bd = count(cof, "closing", 150, "g")
        self.assertEqual(st, 200)
        # Potato: 1000 g received, 5 plates sold -> close at 0.
        st, bd = self.call("POST", "/api/day/receipt",
                           {"date": day, "material_id": pot,
                            "qty_entered": 1.0,
                            "unit_id": units["potato"]["kg"], "user_id": uid})
        self.assertEqual(st, 200)
        st, bd = self.call("POST", "/api/day/sale",
                           {"date": day, "product_id": pot_p,
                            "qty_sold": 5, "user_id": uid})
        self.assertEqual(st, 200)
        st, bd = count(pot, "closing", 0, "g")
        self.assertEqual(st, 200)

        # Day view + close.
        st, body = self.get("/api/day?date=" + day)
        self.assertEqual(st, 200)
        self.assertEqual(body["status"], "open")
        st, bd = self.call("POST", "/api/day/close",
                           {"date": day, "user_id": uid})
        self.assertEqual(st, 200, bd)
        lines = {ln["name"]: ln for ln in bd["report"]["lines"]}
        self.assertEqual(lines["tea"]["qty_sold"], 20)
        # Coffee = 30 cups consumed - 20 tea = 10 cups.
        self.assertEqual(lines["coffee"]["qty_sold"], 10)
        self.assertEqual(lines["potato plate"]["qty_sold"], 5)
        rec = bd["report"]["reconciliation"]
        self.assertEqual(rec["difference"], 0)
        self.assertEqual(bd["report"]["total_profit"],
                         bd["report"]["total_revenue"]
                         - bd["report"]["total_cost"])

        # Closed day is immutable...
        st, bd = count(tea, "closing", 4, "piece")
        self.assertEqual(st, 403)
        # ...but corrections land as adjustment rows with a reason.
        st, bd = self.call("POST", "/api/day/adjust",
                           {"date": day, "material_id": tea,
                            "delta_base": -1, "reason": "recount",
                            "user_id": uid})
        self.assertEqual(st, 200)
        # Next day opening carries the adjustment forward (5 -> 5-1 = 4).
        st, body = self.get("/api/day?date=2026-10-02")
        self.assertEqual(st, 200)
        tea_row = [c for c in body["counts"] if c["name"] == "tea"][0]
        self.assertEqual(tea_row["opening_default_base"], 4)

        # CSV export covers the closed day.
        st, csv = self.get("/api/export.csv?from=2026-10-01&to=2026-10-01")
        self.assertEqual(st, 200)
        self.assertIn("tea", csv)
        self.assertIn("2026-10-01", csv)

    def test_03_closing_before_opening(self):
        st, body = self.get("/api/session")
        uid = body["users"][0]["id"]
        st, mats = self.get("/api/materials")
        pot = [m for m in mats["materials"] if m["name"] == "potato"][0]
        gram = [u for u in pot["units"] if u["unit_name"] == "g"][0]["id"]
        day = "2026-10-05"
        # No opening typed yet: closing lands on the defaulted opening row.
        st, bd = self.call("POST", "/api/day/count",
                           {"date": day, "material_id": pot["id"],
                            "field": "closing", "qty_entered": 0.0,
                            "unit_id": gram, "user_id": uid})
        self.assertEqual(st, 200, bd)
        st, body = self.get("/api/day?date=" + day)
        row = [c for c in body["counts"] if c["name"] == "potato"][0]
        self.assertIsNotNone(row["count"])
        self.assertEqual(row["count"]["opening_base"],
                         row["opening_default_base"])
        self.assertEqual(row["count"]["opening_qty_entered"],
                         row["opening_default_base"])

    def test_02_reason_and_spike_flows(self):
        st, body = self.get("/api/session")
        uid = body["users"][0]["id"]
        st, mats = self.get("/api/materials")
        tea = [m for m in mats["materials"] if m["name"] == "tea"][0]
        piece = [u for u in tea["units"] if u["unit_name"] == "piece"][0]["id"]
        day = "2026-10-02"
        # Opening differs from default (4): reason required.
        st, bd = self.call("POST", "/api/day/count",
                           {"date": day, "material_id": tea["id"],
                            "field": "opening", "qty_entered": 50.0,
                            "unit_id": piece, "user_id": uid})
        self.assertEqual(st, 400)
        self.assertEqual(bd["error"], "opening_reason_required")
        st, bd = self.call("POST", "/api/day/count",
                           {"date": day, "material_id": tea["id"],
                            "field": "opening", "qty_entered": 51.0,
                            "unit_id": piece, "user_id": uid,
                            "reason": "found box from yesterday"})
        self.assertEqual(st, 200)
        # Spike warning: 51 vs 14-day average of 5 (10x = 50).
        self.assertTrue(bd["warnings"])
        # Closing above opening + received without reason: blocked.
        st, bd = self.call("POST", "/api/day/count",
                           {"date": day, "material_id": tea["id"],
                            "field": "closing", "qty_entered": 60.0,
                            "unit_id": piece, "user_id": uid})
        self.assertEqual(st, 400)
        self.assertEqual(bd["error"], "closing_reason_required")
        st, bd = self.call("POST", "/api/day/count",
                           {"date": day, "material_id": tea["id"],
                            "field": "closing", "qty_entered": 60.0,
                            "unit_id": piece, "user_id": uid,
                            "reason": "miscount, confirmed"})
        self.assertEqual(st, 200)

    def test_04_money_archive_and_admin(self):
        st, body = self.get("/api/session")
        uid = body["users"][0]["id"]
        st, mats = self.get("/api/materials")
        tea = [m for m in mats["materials"] if m["name"] == "tea"][0]
        box = [u for u in tea["units"] if u["unit_name"] == "box"][0]["id"]
        st, prods = self.get("/api/products")
        tea_p = [p for p in prods["products"] if p["name"] == "tea"][0]

        # EGP cost input (string with 2 decimals) stores 8025 piasters.
        st, bd = self.call("POST", "/api/costs",
                           {"material_id": tea["id"], "unit_id": box,
                            "price_egp": "80.25",
                            "effective_date": "2026-10-10", "user_id": uid})
        self.assertEqual(st, 200, bd)
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT price_piasters FROM material_costs"
                " WHERE material_id = ? ORDER BY id DESC LIMIT 1",
                (tea["id"],)).fetchone()
            self.assertEqual(row[0], 8025)
        finally:
            conn.close()
        # Rejected: 3 decimals, both fields, neither field.
        for bad in ({"price_egp": "10.123"}, {"price_egp": "10",
                                              "price_piasters": 1000}, {}):
            payload = {"material_id": tea["id"], "unit_id": box,
                       "effective_date": "2026-10-10", "user_id": uid}
            payload.update(bad)
            st, _bd = self.call("POST", "/api/costs", payload)
            self.assertEqual(st, 400, bad)
        # EGP selling price works too.
        st, bd = self.call("POST", "/api/prices",
                           {"product_id": tea_p["id"], "price_egp": 20,
                            "effective_date": "2026-10-10", "user_id": uid})
        self.assertEqual(st, 200, bd)

        # Archive list: slim rows with revenue/cost/profit.
        st, body = self.get("/api/days?from=2026-10-01&to=2026-10-05")
        self.assertEqual(st, 200)
        by_date = {d["date"]: d for d in body["days"]}
        self.assertEqual(by_date["2026-10-01"]["status"], "closed")
        for key in ("revenue", "cost", "profit", "status", "date"):
            self.assertIn(key, by_date["2026-10-01"])
        self.assertNotIn("lines", by_date["2026-10-01"])

        # Day report carries explicit drink cups. (Tea shows 21, not 20:
        # test_01's -1 recount adjustment flows into the report.)
        st, body = self.get("/api/day?date=2026-10-01")
        rep = body["report"]
        self.assertEqual(rep["total_cups"], 30)
        self.assertEqual({d["name"]: d["cups"]
                          for d in rep["cups_by_drink"]},
                         {"tea": 21, "coffee": 9})

        # Rename a product (history intact) and deactivate a material.
        st, bd = self.call("POST", "/api/products/%d/rename" % tea_p["id"],
                           {"name": "green tea", "user_id": uid})
        self.assertEqual(st, 200, bd)
        st, prods = self.get("/api/products")
        self.assertIn("green tea", [p["name"] for p in prods["products"]])
        st, bd = self.call("POST", "/api/materials/%d/set_active"
                           % tea["id"], {"active": 0, "user_id": uid})
        self.assertEqual(st, 200, bd)
        st, mats = self.get("/api/materials")
        self.assertNotIn(tea["id"], [m["id"] for m in mats["materials"]])
        # Bad admin calls.
        st, _bd = self.call("POST", "/api/products/9999/rename",
                            {"name": "x", "user_id": uid})
        self.assertEqual(st, 404)
        st, _bd = self.call("POST", "/api/products/%d/set_active" % tea_p["id"],
                            {"active": 2, "user_id": uid})
        self.assertEqual(st, 400)
        st, _bd = self.call("POST", "/api/products/%d/frobnicate" % tea_p["id"],
                            {"user_id": uid})
        self.assertEqual(st, 404)
        # Restore names/state for a clean fixture.
        self.call("POST", "/api/products/%d/rename" % tea_p["id"],
                  {"name": "tea", "user_id": uid})
        self.call("POST", "/api/materials/%d/set_active" % tea["id"],
                  {"active": 1, "user_id": uid})
        st, body = self.get("/api/session")
        uid = body["users"][0]["id"]
        st, mats = self.get("/api/materials")
        tea = [m for m in mats["materials"] if m["name"] == "tea"][0]
        piece = [u for u in tea["units"] if u["unit_name"] == "piece"][0]["id"]
        day = "2026-10-02"
        # Opening differs from default (4): reason required.
        st, bd = self.call("POST", "/api/day/count",
                           {"date": day, "material_id": tea["id"],
                            "field": "opening", "qty_entered": 50.0,
                            "unit_id": piece, "user_id": uid})
        self.assertEqual(st, 400)
        self.assertEqual(bd["error"], "opening_reason_required")
        st, bd = self.call("POST", "/api/day/count",
                           {"date": day, "material_id": tea["id"],
                            "field": "opening", "qty_entered": 51.0,
                            "unit_id": piece, "user_id": uid,
                            "reason": "found box from yesterday"})
        self.assertEqual(st, 200)
        # Spike warning: 51 vs 14-day average of 5 (10x = 50).
        self.assertTrue(bd["warnings"])
        # Closing above opening + received without reason: blocked.
        st, bd = self.call("POST", "/api/day/count",
                           {"date": day, "material_id": tea["id"],
                            "field": "closing", "qty_entered": 60.0,
                            "unit_id": piece, "user_id": uid})
        self.assertEqual(st, 400)
        self.assertEqual(bd["error"], "closing_reason_required")
        st, bd = self.call("POST", "/api/day/count",
                           {"date": day, "material_id": tea["id"],
                            "field": "closing", "qty_entered": 60.0,
                            "unit_id": piece, "user_id": uid,
                            "reason": "miscount, confirmed"})
        self.assertEqual(st, 200)


if __name__ == "__main__":
    unittest.main()
