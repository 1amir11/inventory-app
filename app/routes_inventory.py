# routes_inventory.py - JSON API for daily stock counts, products and reports.
#
# Every write requires {"user_id": <id>} in the JSON body (phase 1 user
# picker; PIN comes in phase 2). Every write runs in ONE transaction and
# writes an audit_log row. Writes to a closed day fail with 403 except
# POST /api/day/adjust (correction rows with a mandatory reason).
#
# Standard library only, Python 3.8 compatible.

import json
import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import calc  # noqa: E402
import db  # noqa: E402
import http_kit  # noqa: E402
import strings_ar  # noqa: E402
from http_kit import ApiError  # noqa: E402

S = strings_ar.STRINGS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _body(request):
    if not request.is_json_content_type():
        raise ApiError(400, "json_required", S["err_invalid"])
    return request.json()


def _user_id(conn, body, required=True):
    uid = body.get("user_id")
    if uid is None:
        if required:
            raise ApiError(401, "login_required", S["err_user_required"])
        return None
    if not isinstance(uid, int):
        raise ApiError(400, "invalid_user", S["err_invalid"])
    row = conn.execute("SELECT id FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None:
        raise ApiError(401, "login_required", S["err_user_required"])
    return uid


def _date(value):
    if not calc.valid_business_date(value or ""):
        raise ApiError(400, "bad_date", S["err_bad_date"])
    return value


def _audit(conn, user_id, action, entity, entity_id=None, business_date=None,
           before=None, after=None, reason=None):
    conn.execute(
        "INSERT INTO audit_log (user_id, action, entity, entity_id,"
        " business_date, before_json, after_json, reason, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, action, entity, entity_id, business_date,
         json.dumps(before, ensure_ascii=False) if before is not None else None,
         json.dumps(after, ensure_ascii=False) if after is not None else None,
         reason, db.now_iso()))


def _parse_money(body, code="bad_price"):
    # type: (dict, str) -> int
    """Price in piasters from either "price_piasters" (int) or "price_egp"
    (string/number with up to 2 decimals). Staff type EGP; the UI never asks
    for piasters. Both present, or neither, is a 400."""
    has_p = body.get("price_piasters") is not None
    has_e = body.get("price_egp") is not None
    if has_p == has_e:
        raise ApiError(400, code, S["err_invalid"])
    if has_e:
        try:
            amount = calc.egp_to_piasters(body.get("price_egp"))
        except ValueError:
            raise ApiError(400, code, S["err_invalid"])
    else:
        try:
            amount = int(body.get("price_piasters"))
        except (TypeError, ValueError):
            raise ApiError(400, code, S["err_invalid"])
    err = calc.check_price_piasters(amount)
    if err:
        raise ApiError(400, code, S["err_invalid"])
    return amount


def _material_or_400(conn, material_id):
    row = conn.execute("SELECT * FROM materials WHERE id = ?",
                       (material_id,)).fetchone()
    if row is None:
        raise ApiError(404, "not_found", S["err_not_found"])
    return row


def _unit_of(conn, unit_id, material_id):
    row = conn.execute(
        "SELECT * FROM count_units WHERE id = ? AND material_id = ?"
        " AND active = 1", (unit_id, material_id)).fetchone()
    if row is None:
        raise ApiError(400, "bad_unit", S["err_invalid"])
    return row


def _product_or_400(conn, product_id):
    row = conn.execute("SELECT * FROM products WHERE id = ?",
                       (product_id,)).fetchone()
    if row is None:
        raise ApiError(404, "not_found", S["err_not_found"])
    return row


def _products_for_calc(conn, business_date):
    """Active products as calc.compute_day_summary expects."""
    recipes = db.recipes_as_of(conn, business_date)
    out = []
    for row in db.list_products(conn):
        out.append({
            "id": row["id"], "name": row["name"],
            "sold_source": row["sold_source"],
            "source_material_id": row["source_material_id"],
            "recipe_qty_base": row["recipe_qty_base"],
            "coffee_material_id": row["coffee_material_id"],
            "uses_cup": bool(row["uses_cup"]),
            "recipe": recipes.get(row["id"], []),
        })
    return out


def _day_consumed(conn, business_date):
    """{material_id: effective consumed base units} for every counted material."""
    out = {}
    rows = conn.execute(
        "SELECT * FROM stock_counts WHERE business_date = ?",
        (business_date,)).fetchall()
    for row in rows:
        received = db.received_total(conn, row["material_id"], business_date)
        adj = db.adjustments_total(conn, row["material_id"], business_date)
        closing = row["closing_base"]
        if closing is None:
            continue
        out[row["material_id"]] = (row["opening_base"] + received
                                   - closing - adj)
    return out


def _cup_material_ids(conn):
    rows = conn.execute(
        "SELECT id FROM materials WHERE is_cup = 1 AND active = 1").fetchall()
    return [r["id"] for r in rows]


def _yield_pairs(conn, end_date, window_days, coffee_material_id,
                 coffee_product_ids):
    """[(grams, cups)] per day before end_date (newest first, up to window).

    cups for a day come from the same remainder rule the report uses, so the
    measured yield is consistent with what the owner sees."""
    pairs = []
    days = conn.execute(
        "SELECT business_date FROM business_days WHERE business_date < ?"
        " AND status = 'closed' ORDER BY business_date DESC LIMIT ?",
        (end_date, window_days)).fetchall()
    for day_row in days:
        day = day_row["business_date"]
        consumed = _day_consumed(conn, day)
        grams = consumed.get(coffee_material_id, 0)
        products = _products_for_calc(conn, day)
        cups_consumed = sum(consumed.get(mid, 0)
                            for mid in _cup_material_ids(conn))
        summary = calc.compute_day_summary(
            products, consumed, db.prices_as_of(conn, day),
            db.costs_as_of(conn, day), cups_consumed,
            manual_sales=_manual_sales(conn, day), coffee_gpc=None)
        cups = 0
        for line in summary["lines"]:
            if line["product_id"] in coffee_product_ids:
                cups += line["qty_sold"]
        if cups > 0:
            pairs.append((grams, cups))
    return pairs


def _manual_sales(conn, business_date):
    out = {}
    rows = conn.execute(
        "SELECT product_id, qty_sold FROM product_sales WHERE business_date = ?",
        (business_date,)).fetchall()
    for row in rows:
        out[row["product_id"]] = row["qty_sold"]
    return out


def _coffee_yield_for(conn, business_date):
    """Measured yield before business_date; fallback all history, then the
    initial manual estimate from settings."""
    try:
        window = int(db.get_setting(conn, "yield_window_days"))
    except ValueError:
        window = 30
    try:
        fallback_gpc = float(db.get_setting(conn, "initial_gpc"))
    except ValueError:
        fallback_gpc = 10.0
    try:
        bag = int(db.get_setting(conn, "coffee_bag_grams"))
    except ValueError:
        bag = 250
    coffee_products = conn.execute(
        "SELECT id FROM products WHERE sold_source ="
        " 'derived_remainder_of_cup' AND active = 1").fetchall()
    coffee_pids = [r["id"] for r in coffee_products]
    coffee_mats = conn.execute(
        "SELECT DISTINCT coffee_material_id FROM products"
        " WHERE coffee_material_id IS NOT NULL").fetchall()
    if not coffee_mats or not coffee_pids:
        return {"grams_per_cup": fallback_gpc,
                "cups_per_bag": bag / fallback_gpc if fallback_gpc else 0.0,
                "days_used": 0, "cups_used": 0, "confidence": "none",
                "source": "estimate"}, fallback_gpc
    coffee_mid = coffee_mats[0]["coffee_material_id"]
    pairs = _yield_pairs(conn, business_date, window, coffee_mid, coffee_pids)
    if not pairs:
        pairs = _yield_pairs(conn, business_date, 100000, coffee_mid,
                             coffee_pids)
    return calc.coffee_yield(pairs, bag, fallback_gpc), fallback_gpc


def build_day_report(conn, business_date):
    """Full recomputed report for one day (pure calc on effective data)."""
    products = _products_for_calc(conn, business_date)
    consumed = _day_consumed(conn, business_date)
    prices = db.prices_as_of(conn, business_date)
    costs = db.costs_as_of(conn, business_date)
    cups_consumed = sum(consumed.get(mid, 0)
                        for mid in _cup_material_ids(conn))
    manual = _manual_sales(conn, business_date)
    yield_info, _fb = _coffee_yield_for(conn, business_date)
    material_names = {m["id"]: m["name"] for m in db.list_materials(
        conn, active_only=False)}
    gpc = yield_info["grams_per_cup"] if yield_info["source"] == "measured" \
        else None
    # An estimate still prices coffee (flagged), so the owner sees numbers.
    if gpc is None:
        try:
            gpc = float(db.get_setting(conn, "initial_gpc"))
        except ValueError:
            gpc = 10.0
    summary = calc.compute_day_summary(products, consumed, prices, costs,
                                       cups_consumed, manual_sales=manual,
                                       coffee_gpc=gpc,
                                       material_names=material_names)
    if yield_info["source"] == "estimate":
        summary["warnings"].append("coffee cost uses the initial estimate"
                                  " (no measured history yet)")
    summary["yield"] = yield_info
    check = conn.execute(
        "SELECT counted_cups FROM coffee_checks WHERE business_date = ?",
        (business_date,)).fetchone()
    if check is not None and check["counted_cups"] is not None:
        derived = 0
        for line in summary["lines"]:
            prod = conn.execute("SELECT sold_source FROM products WHERE id = ?",
                                (line["product_id"],)).fetchone()
            if prod is not None and prod["sold_source"] == "derived_remainder_of_cup":
                derived += line["qty_sold"]
        ok, tol = calc.coffee_crosscheck(derived, check["counted_cups"])
        summary["coffee_check"] = {"counted": check["counted_cups"],
                                  "derived": derived, "ok": ok,
                                  "tolerance": tol}
        if not ok:
            summary["warnings"].append(S["warn_coffee_check"])
    return summary


# ---------------------------------------------------------------------------
# Public: session probe (launcher single-instance check MUST stay public),
# strings, users, settings
# ---------------------------------------------------------------------------

def api_session(context, request):
    conn = context.connect()
    try:
        users = [{"id": r["id"], "name": r["name"]}
                 for r in conn.execute("SELECT id, name FROM users ORDER BY id")]
        return http_kit.json_response({
            "app": "kitchen_inventory",
            "authenticated": False,
            "setup_required": len(users) == 0,
            "users": users,
        })
    finally:
        conn.close()


def api_strings(context, request):
    return http_kit.json_response(
        {key: S[key] for key in strings_ar.JS_KEYS})


def api_list_users(context, request):
    conn = context.connect()
    try:
        users = [{"id": r["id"], "name": r["name"]}
                 for r in conn.execute("SELECT id, name FROM users ORDER BY id")]
        return http_kit.json_response({"users": users})
    finally:
        conn.close()


def api_create_user(context, request):
    body = _body(request)
    name = (body.get("name") or "").strip()
    if not name or len(name) > 100:
        raise ApiError(400, "bad_name", S["err_invalid"])
    conn = context.connect()
    try:
        existing = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if existing >= 2:
            raise ApiError(400, "too_many_users", S["err_invalid"])
        creator = None
        if existing > 0:
            creator = _user_id(conn, body)
        with conn:
            conn.execute("INSERT INTO users (name, created_at) VALUES (?, ?)",
                         (name, db.now_iso()))
            uid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            _audit(conn, creator, "create", "user", uid,
                   after={"name": name})
        return http_kit.json_response({"ok": True, "id": uid})
    finally:
        conn.close()


def api_get_settings(context, request):
    conn = context.connect()
    try:
        return http_kit.json_response({"settings": {
            "initial_gpc": db.get_setting(conn, "initial_gpc"),
            "coffee_bag_grams": db.get_setting(conn, "coffee_bag_grams"),
            "yield_window_days": db.get_setting(conn, "yield_window_days"),
            "demo": db.get_setting(conn, "demo") or "0",
        }})
    finally:
        conn.close()


def api_put_settings(context, request):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        with conn:
            for key in ("initial_gpc", "coffee_bag_grams", "yield_window_days"):
                if key in body:
                    try:
                        number = float(body[key])
                    except (TypeError, ValueError):
                        raise ApiError(400, "bad_setting", S["err_invalid"])
                    if number <= 0 or number > 100000:
                        raise ApiError(400, "bad_setting", S["err_invalid"])
                    db.set_setting(conn, key, str(body[key]), uid)
            _audit(conn, uid, "update", "settings", after=body)
        return http_kit.json_response({"ok": True})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Materials, units, costs
# ---------------------------------------------------------------------------

def api_list_materials(context, request):
    conn = context.connect()
    try:
        out = []
        for mat in db.list_materials(conn):
            units = [{"id": u["id"], "unit_name": u["unit_name"],
                      "factor_to_base": u["factor_to_base"],
                      "is_base_unit": u["is_base_unit"]}
                     for u in db.units_for(conn, mat["id"])]
            out.append({"id": mat["id"], "name": mat["name"],
                        "department": mat["department"],
                        "base_unit": mat["base_unit"],
                        "is_cup": bool(mat["is_cup"]), "units": units})
        return http_kit.json_response({"materials": out})
    finally:
        conn.close()


def api_create_material(context, request):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        name = (body.get("name") or "").strip()
        dept = body.get("department")
        base_unit = body.get("base_unit")
        is_cup = 1 if body.get("is_cup") else 0
        if not name or dept not in ("kitchen", "cafeteria") \
                or base_unit not in ("g", "ml", "piece"):
            raise ApiError(400, "bad_material", S["err_invalid"])
        with conn:
            conn.execute(
                "INSERT INTO materials (name, department, base_unit, is_cup,"
                " created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, dept, base_unit, is_cup, uid, db.now_iso()))
            mid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            conn.execute(
                "INSERT INTO count_units (material_id, unit_name,"
                " factor_to_base, is_base_unit, created_by, created_at)"
                " VALUES (?, ?, 1, 1, ?, ?)",
                (mid, base_unit, uid, db.now_iso()))
            # Optional extra units + first cost in the same transaction.
            for unit in body.get("units") or []:
                _insert_unit(conn, mid, unit, uid)
            cost = body.get("first_cost")
            if cost:
                _insert_cost(conn, mid, cost, uid)
            _audit(conn, uid, "create", "material", mid,
                   after={"name": name})
        return http_kit.json_response({"ok": True, "id": mid})
    finally:
        conn.close()


def _insert_unit(conn, material_id, unit, uid):
    uname = (unit.get("unit_name") or "").strip()
    try:
        factor = int(unit.get("factor_to_base"))
    except (TypeError, ValueError):
        raise ApiError(400, "bad_unit", S["err_invalid"])
    if not uname:
        raise ApiError(400, "bad_unit", S["err_invalid"])
    if factor <= 0:
        raise ApiError(400, "bad_unit", S["err_invalid"])
    conn.execute(
        "INSERT INTO count_units (material_id, unit_name, factor_to_base,"
        " created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (material_id, uname, factor, uid, db.now_iso()))
    return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def api_add_unit(context, request):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        _material_or_400(conn, int(body.get("material_id") or 0))
        with conn:
            unit_id = _insert_unit(conn, int(body["material_id"]), body, uid)
            _audit(conn, uid, "create", "count_unit", unit_id,
                   after={"material_id": body["material_id"]})
        return http_kit.json_response({"ok": True, "id": unit_id})
    finally:
        conn.close()


def _insert_cost(conn, material_id, cost, uid):
    price = _parse_money(cost, "bad_cost")
    try:
        unit_id = int(cost.get("unit_id"))
    except (TypeError, ValueError):
        raise ApiError(400, "bad_cost", S["err_invalid"])
    eff = cost.get("effective_date") or ""
    if not calc.valid_business_date(eff):
        raise ApiError(400, "bad_date", S["err_bad_date"])
    _unit_of(conn, unit_id, material_id)
    conn.execute(
        "INSERT INTO material_costs (material_id, count_unit_id,"
        " price_piasters, effective_date, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (material_id, unit_id, price, eff, uid, db.now_iso()))


def api_add_cost(context, request):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        _material_or_400(conn, int(body.get("material_id") or 0))
        with conn:
            _insert_cost(conn, int(body["material_id"]), body, uid)
            _audit(conn, uid, "create", "material_cost",
                   after={"material_id": body["material_id"]})
        return http_kit.json_response({"ok": True})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Products, prices, recipes
# ---------------------------------------------------------------------------

def api_list_products(context, request):
    conn = context.connect()
    try:
        out = []
        for prod in db.list_products(conn):
            out.append({"id": prod["id"], "name": prod["name"],
                        "department": prod["department"],
                        "sold_source": prod["sold_source"],
                        "source_material_id": prod["source_material_id"],
                        "recipe_qty_base": prod["recipe_qty_base"],
                        "coffee_material_id": prod["coffee_material_id"],
                        "uses_cup": bool(prod["uses_cup"])})
        return http_kit.json_response({"products": out})
    finally:
        conn.close()


def api_create_product(context, request):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        name = (body.get("name") or "").strip()
        dept = body.get("department")
        source = body.get("sold_source")
        if not name or dept not in ("kitchen", "cafeteria") or source not in (
                "derived_from_material", "derived_remainder_of_cup", "manual"):
            raise ApiError(400, "bad_product", S["err_invalid"])
        source_mid = body.get("source_material_id")
        recipe_qty_base = None
        if source == "derived_from_material":
            if not source_mid:
                raise ApiError(400, "bad_product", S["err_invalid"])
            _material_or_400(conn, int(source_mid))
            try:
                qty_entered = float(body.get("recipe_qty_entered"))
                unit_id = int(body.get("recipe_unit_id"))
            except (TypeError, ValueError):
                raise ApiError(400, "bad_product", S["err_invalid"])
            _unit_of(conn, unit_id, int(source_mid))
            recipe_qty_base = calc.to_base_qty(qty_entered,
                                              _unit_factor(conn, unit_id))
            if recipe_qty_base <= 0:
                raise ApiError(400, "bad_product", S["err_invalid"])
        coffee_mid = body.get("coffee_material_id")
        if source == "derived_remainder_of_cup":
            if not coffee_mid:
                raise ApiError(400, "bad_product", S["err_invalid"])
            _material_or_400(conn, int(coffee_mid))
        uses_cup = 1 if body.get("uses_cup") else 0
        with conn:
            conn.execute(
                "INSERT INTO products (name, department, sold_source,"
                " source_material_id, recipe_qty_base, coffee_material_id,"
                " uses_cup, created_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, dept, source, source_mid, recipe_qty_base, coffee_mid,
                 uses_cup, uid, db.now_iso()))
            pid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            price = body.get("first_price")
            if price is not None:
                _insert_price(conn, pid, price, uid)
            _audit(conn, uid, "create", "product", pid, after={"name": name})
        return http_kit.json_response({"ok": True, "id": pid})
    finally:
        conn.close()


def _unit_factor(conn, unit_id):
    row = conn.execute("SELECT factor_to_base FROM count_units WHERE id = ?",
                       (unit_id,)).fetchone()
    return row["factor_to_base"]


def _insert_price(conn, product_id, price, uid):
    if not isinstance(price, dict):
        raise ApiError(400, "bad_price", S["err_invalid"])
    amount = _parse_money(price)
    eff = price.get("effective_date") or ""
    if not calc.valid_business_date(eff):
        raise ApiError(400, "bad_date", S["err_bad_date"])
    conn.execute(
        "INSERT INTO product_prices (product_id, price_piasters,"
        " effective_date, created_by, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (product_id, amount, eff, uid, db.now_iso()))


def api_add_price(context, request):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        _product_or_400(conn, int(body.get("product_id") or 0))
        with conn:
            _insert_price(conn, int(body["product_id"]), body, uid)
            _audit(conn, uid, "create", "product_price",
                   after={"product_id": body["product_id"]})
        return http_kit.json_response({"ok": True})
    finally:
        conn.close()


def api_add_recipe(context, request):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        _product_or_400(conn, int(body.get("product_id") or 0))
        _material_or_400(conn, int(body.get("material_id") or 0))
        try:
            qty_entered = float(body.get("qty_entered"))
            unit_id = int(body.get("unit_id"))
        except (TypeError, ValueError):
            raise ApiError(400, "bad_recipe", S["err_invalid"])
        err = calc.check_entered_qty(qty_entered)
        if err:
            raise ApiError(400, "bad_recipe", S["err_invalid"])
        eff = body.get("effective_date") or ""
        if not calc.valid_business_date(eff):
            raise ApiError(400, "bad_date", S["err_bad_date"])
        unit = _unit_of(conn, unit_id, int(body["material_id"]))
        qty_base = calc.to_base_qty(qty_entered, unit["factor_to_base"])
        with conn:
            conn.execute(
                "INSERT INTO recipe_lines (product_id, material_id, qty_base,"
                " effective_date, created_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (int(body["product_id"]), int(body["material_id"]), qty_base,
                 eff, uid, db.now_iso()))
            _audit(conn, uid, "create", "recipe_line",
                   after={"product_id": body["product_id"]})
        return http_kit.json_response({"ok": True, "qty_base": qty_base})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Day view, counts, receipts, sales, close, adjust
# ---------------------------------------------------------------------------

def api_day(context, request):
    date = _date(request.query.get("date") or "")
    conn = context.connect()
    try:
        status = db.day_status(conn, date)
        counts = []
        for mat in db.list_materials(conn):
            row = conn.execute(
                "SELECT * FROM stock_counts WHERE business_date = ?"
                " AND material_id = ?", (date, mat["id"])).fetchone()
            received = db.received_total(conn, mat["id"], date)
            avg = db.average14(conn, mat["id"], date)
            default_open = db.effective_closing(conn, mat["id"], date)
            units = [{"id": u["id"], "unit_name": u["unit_name"],
                      "factor_to_base": u["factor_to_base"],
                      "is_base_unit": u["is_base_unit"]}
                     for u in db.units_for(conn, mat["id"])]
            item = {"material_id": mat["id"], "name": mat["name"],
                    "department": mat["department"],
                    "base_unit": mat["base_unit"],
                    "is_cup": bool(mat["is_cup"]),
                    "received_base": received,
                    "opening_default_base": default_open,
                    "avg14": avg, "units": units,
                    "count": dict(row) if row is not None else None}
            counts.append(item)
        receipts = [dict(r) for r in conn.execute(
            "SELECT rr.*, u.unit_name FROM receipt_rows rr"
            " JOIN count_units u ON u.id = rr.unit_id"
            " WHERE rr.business_date = ? ORDER BY rr.id", (date,))]
        sales = [dict(r) for r in conn.execute(
            "SELECT ps.*, p.name FROM product_sales ps"
            " JOIN products p ON p.id = ps.product_id"
            " WHERE ps.business_date = ? ORDER BY ps.id", (date,))]
        products = [{"id": p["id"], "name": p["name"],
                     "sold_source": p["sold_source"]} for p in
                    db.list_products(conn)]
        report = None
        if status is not None:
            report = build_day_report(conn, date)
        return http_kit.json_response({
            "date": date, "status": status or "new",
            "counts": counts, "receipts": receipts, "sales": sales,
            "products": products, "report": report,
        })
    finally:
        conn.close()


def api_set_count(context, request):
    body = _body(request)
    date = _date(body.get("date") or "")
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        material_id = int(body.get("material_id") or 0)
        field = body.get("field")
        _material_or_400(conn, material_id)
        if field not in ("opening", "closing"):
            raise ApiError(400, "bad_field", S["err_invalid"])
        try:
            qty_entered = float(body.get("qty_entered"))
            unit_id = int(body.get("unit_id"))
        except (TypeError, ValueError):
            raise ApiError(400, "bad_qty", S["err_invalid"])
        err = calc.check_entered_qty(qty_entered)
        if err:
            raise ApiError(400, "bad_qty", S["err_invalid"])
        unit = _unit_of(conn, unit_id, material_id)
        base = calc.to_base_qty(qty_entered, unit["factor_to_base"])
        err = calc.check_base_qty(base)
        if err:
            raise ApiError(400, "bad_qty", S["err_invalid"])
        reason = (body.get("reason") or "").strip() or None
        db.ensure_day(conn, date, uid)
        try:
            db.require_open(conn, date)
        except db.DayClosedError:
            raise ApiError(403, "day_closed", S["err_day_closed"])
        with conn:
            row = conn.execute(
                "SELECT * FROM stock_counts WHERE business_date = ?"
                " AND material_id = ?", (date, material_id)).fetchone()
            before = dict(row) if row is not None else None
            if field == "opening":
                default = db.effective_closing(conn, material_id, date)
                if base != default and not reason:
                    raise ApiError(400, "opening_reason_required",
                                   S["err_opening_differs"],
                                   {"opening_default_base": default})
                if row is None:
                    conn.execute(
                        "INSERT INTO stock_counts (business_date, material_id,"
                        " opening_base, opening_qty_entered, opening_unit_id,"
                        " opening_reason, created_by, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (date, material_id, base, qty_entered, unit_id,
                         reason, uid, db.now_iso()))
                else:
                    conn.execute(
                        "UPDATE stock_counts SET opening_base = ?,"
                        " opening_qty_entered = ?, opening_unit_id = ?,"
                        " opening_reason = ? WHERE id = ?",
                        (base, qty_entered, unit_id, reason, row["id"]))
            else:
                opening = row["opening_base"] if row is not None else \
                    db.effective_closing(conn, material_id, date)
                received = db.received_total(conn, material_id, date)
                if calc.closing_needs_reason(opening, received, base) \
                        and not reason:
                    raise ApiError(400, "closing_reason_required",
                                   S["err_negative_close"],
                                   {"opening_base": opening,
                                    "received_base": received})
                if row is None:
                    # Opening not typed yet: default from yesterday. The
                    # entered/unit pair mirrors the default in the BASE unit
                    # so the stored row is self-consistent.
                    base_unit = conn.execute(
                        "SELECT * FROM count_units WHERE material_id = ?"
                        " AND is_base_unit = 1", (material_id,)).fetchone()
                    conn.execute(
                        "INSERT INTO stock_counts (business_date, material_id,"
                        " opening_base, opening_qty_entered, opening_unit_id,"
                        " closing_base, closing_qty_entered, closing_unit_id,"
                        " closing_reason, created_by, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (date, material_id, opening,
                         calc.to_entered_qty(opening,
                                             base_unit["factor_to_base"]),
                         base_unit["id"], base,
                         qty_entered, unit_id, reason, uid, db.now_iso()))
                else:
                    conn.execute(
                        "UPDATE stock_counts SET closing_base = ?,"
                        " closing_qty_entered = ?, closing_unit_id = ?,"
                        " closing_reason = ? WHERE id = ?",
                        (base, qty_entered, unit_id, reason, row["id"]))
            after = conn.execute(
                "SELECT * FROM stock_counts WHERE business_date = ?"
                " AND material_id = ?", (date, material_id)).fetchone()
            _audit(conn, uid, "set_%s" % field, "stock_count",
                   after["id"] if after else None, date, before,
                   dict(after) if after else None, reason)
        warnings = []
        if calc.is_spike(base, db.average14(conn, material_id, date)):
            warnings.append(S["warn_spike"])
        return http_kit.json_response({"ok": True, "qty_base": base,
                                       "warnings": warnings})
    finally:
        conn.close()


def api_add_receipt(context, request):
    body = _body(request)
    date = _date(body.get("date") or "")
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        material_id = int(body.get("material_id") or 0)
        _material_or_400(conn, material_id)
        try:
            qty_entered = float(body.get("qty_entered"))
            unit_id = int(body.get("unit_id"))
        except (TypeError, ValueError):
            raise ApiError(400, "bad_qty", S["err_invalid"])
        err = calc.check_entered_qty(qty_entered)
        if err:
            raise ApiError(400, "bad_qty", S["err_invalid"])
        unit = _unit_of(conn, unit_id, material_id)
        base = calc.to_base_qty(qty_entered, unit["factor_to_base"])
        db.ensure_day(conn, date, uid)
        try:
            db.require_open(conn, date)
        except db.DayClosedError:
            raise ApiError(403, "day_closed", S["err_day_closed"])
        with conn:
            conn.execute(
                "INSERT INTO receipt_rows (business_date, material_id,"
                " qty_entered, unit_id, qty_base, created_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (date, material_id, qty_entered, unit_id, base, uid,
                 db.now_iso()))
            rid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            _audit(conn, uid, "create", "receipt", rid, date,
                   after={"material_id": material_id, "qty_base": base})
        return http_kit.json_response({"ok": True, "id": rid,
                                       "qty_base": base})
    finally:
        conn.close()


def api_set_sale(context, request):
    body = _body(request)
    date = _date(body.get("date") or "")
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        product = _product_or_400(conn, int(body.get("product_id") or 0))
        if product["sold_source"] != "manual":
            raise ApiError(400, "manual_only", S["err_manual_only"])
        try:
            qty = int(body.get("qty_sold"))
        except (TypeError, ValueError):
            raise ApiError(400, "bad_qty", S["err_invalid"])
        err = calc.check_qty_sold(qty)
        if err:
            raise ApiError(400, "bad_qty", S["err_invalid"])
        db.ensure_day(conn, date, uid)
        try:
            db.require_open(conn, date)
        except db.DayClosedError:
            raise ApiError(403, "day_closed", S["err_day_closed"])
        with conn:
            before = conn.execute(
                "SELECT * FROM product_sales WHERE business_date = ?"
                " AND product_id = ?", (date, product["id"])).fetchone()
            if before is None:
                conn.execute(
                    "INSERT INTO product_sales (business_date, product_id,"
                    " qty_sold, created_by, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (date, product["id"], qty, uid, db.now_iso()))
            else:
                conn.execute("UPDATE product_sales SET qty_sold = ? WHERE id = ?",
                             (qty, before["id"]))
            _audit(conn, uid, "set_sale", "product_sale",
                   before["id"] if before else None, date,
                   dict(before) if before else None, {"qty_sold": qty})
        return http_kit.json_response({"ok": True})
    finally:
        conn.close()


def api_coffee_check(context, request):
    body = _body(request)
    date = _date(body.get("date") or "")
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        try:
            counted = int(body.get("counted_cups"))
        except (TypeError, ValueError):
            raise ApiError(400, "bad_qty", S["err_invalid"])
        err = calc.check_qty_sold(counted)
        if err:
            raise ApiError(400, "bad_qty", S["err_invalid"])
        db.ensure_day(conn, date, uid)
        try:
            db.require_open(conn, date)
        except db.DayClosedError:
            raise ApiError(403, "day_closed", S["err_day_closed"])
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO coffee_checks (business_date,"
                " counted_cups, created_by, created_at)"
                " VALUES (?, ?, ?, ?)", (date, counted, uid, db.now_iso()))
            _audit(conn, uid, "set_check", "coffee_check", None, date,
                   after={"counted_cups": counted})
        return http_kit.json_response({"ok": True})
    finally:
        conn.close()


def api_close_day(context, request):
    body = _body(request)
    date = _date(body.get("date") or "")
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        if db.day_status(conn, date) is None:
            raise ApiError(400, "empty_day", S["err_invalid"])
        try:
            db.require_open(conn, date)
        except db.DayClosedError:
            raise ApiError(403, "day_closed", S["err_day_closed"])
        missing = conn.execute(
            "SELECT m.name FROM materials m LEFT JOIN stock_counts c"
            " ON c.material_id = m.id AND c.business_date = ?"
            " WHERE m.active = 1 AND (c.id IS NULL OR c.closing_base IS NULL)"
            " ORDER BY m.id", (date,)).fetchall()
        if missing:
            raise ApiError(400, "missing_close", S["err_missing_close"],
                           {"missing": [r["name"] for r in missing]})
        report = build_day_report(conn, date)
        with conn:
            conn.execute(
                "UPDATE business_days SET status = 'closed', closed_by = ?,"
                " closed_at = ?, snapshot_json = ? WHERE business_date = ?",
                (uid, db.now_iso(),
                 json.dumps(report, ensure_ascii=False), date))
            _audit(conn, uid, "close", "day", None, date, after=report)
        backup_path = None
        try:
            backup_path = db.backup_db(context.db_path)
        except Exception:
            backup_path = None  # closing must not fail over a backup hiccup
        return http_kit.json_response({"ok": True, "report": report,
                                       "backup": backup_path})
    finally:
        conn.close()


def api_adjust(context, request):
    body = _body(request)
    date = _date(body.get("date") or "")
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        material_id = int(body.get("material_id") or 0)
        _material_or_400(conn, material_id)
        try:
            delta = int(body.get("delta_base"))
        except (TypeError, ValueError):
            raise ApiError(400, "bad_qty", S["err_invalid"])
        if delta == 0 or abs(delta) > calc.MAX_BASE_QTY:
            raise ApiError(400, "bad_qty", S["err_invalid"])
        reason = (body.get("reason") or "").strip()
        if not reason:
            raise ApiError(400, "reason_required", S["err_reason_required"])
        if db.day_status(conn, date) != "closed":
            raise ApiError(400, "day_not_closed", S["err_adjust_open"])
        with conn:
            conn.execute(
                "INSERT INTO stock_adjustments (business_date, material_id,"
                " delta_base, reason, created_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (date, material_id, delta, reason, uid, db.now_iso()))
            aid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            _audit(conn, uid, "adjust", "stock_adjustment", aid, date,
                   after={"material_id": material_id, "delta_base": delta},
                   reason=reason)
        return http_kit.json_response({"ok": True, "id": aid})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Yield, range report, CSV export, backups
# ---------------------------------------------------------------------------

def api_yield(context, request):
    conn = context.connect()
    try:
        try:
            window = int(request.query.get("days")
                         or db.get_setting(conn, "yield_window_days"))
        except (TypeError, ValueError):
            window = 30
        window = max(1, min(window, 365))
        date = request.query.get("date") or ""
        if date:
            _date(date)
        else:
            row = conn.execute(
                "SELECT MAX(business_date) AS m FROM business_days").fetchone()
            date = row["m"] or "2026-01-01"
        info, _fb = _coffee_yield_for(conn, date)
        # Re-run with the requested window for the display pair list.
        return http_kit.json_response({"yield": info, "date": date})
    finally:
        conn.close()


def api_range_report(context, request):
    date_from = _date(request.query.get("from") or "")
    date_to = _date(request.query.get("to") or "")
    if date_to < date_from:
        raise ApiError(400, "bad_range", S["err_invalid"])
    conn = context.connect()
    try:
        days = conn.execute(
            "SELECT business_date, status FROM business_days"
            " WHERE business_date BETWEEN ? AND ? ORDER BY business_date",
            (date_from, date_to)).fetchall()
        out_days = []
        totals = {"revenue": 0, "cost": 0, "profit": 0}
        for day in days:
            rep = build_day_report(conn, day["business_date"])
            out_days.append({"date": day["business_date"],
                             "status": day["status"],
                             "revenue": rep["total_revenue"],
                             "cost": rep["total_cost"],
                             "profit": rep["total_profit"],
                             "lines": rep["lines"]})
            totals["revenue"] += rep["total_revenue"]
            totals["cost"] += rep["total_cost"]
            totals["profit"] += rep["total_profit"]
        return http_kit.json_response({"days": out_days, "totals": totals})
    finally:
        conn.close()


def api_days(context, request):
    """Archive list: one slim row per day (date, status, revenue, cost,
    profit). Past days recompute from effective-dated data, so the archive
    always shows each day exactly as recorded."""
    date_from = _date(request.query.get("from") or "")
    date_to = _date(request.query.get("to") or "")
    if date_to < date_from:
        raise ApiError(400, "bad_range", S["err_invalid"])
    conn = context.connect()
    try:
        days = conn.execute(
            "SELECT business_date, status FROM business_days"
            " WHERE business_date BETWEEN ? AND ? ORDER BY business_date",
            (date_from, date_to)).fetchall()
        out = []
        for day in days:
            rep = build_day_report(conn, day["business_date"])
            out.append({"date": day["business_date"],
                        "status": day["status"],
                        "revenue": rep["total_revenue"],
                        "cost": rep["total_cost"],
                        "profit": rep["total_profit"]})
        return http_kit.json_response({"days": out})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Rename / deactivate (soft only: rows are never deleted, history intact)
# ---------------------------------------------------------------------------

def _rename_row(conn, table, item_id, name, uid, entity):
    row = conn.execute("SELECT * FROM %s WHERE id = ?" % table,
                       (item_id,)).fetchone()
    if row is None:
        raise ApiError(404, "not_found", S["err_not_found"])
    clean = (name or "").strip()
    if not clean or len(clean) > 100:
        raise ApiError(400, "bad_name", S["err_invalid"])
    with conn:
        conn.execute("UPDATE %s SET name = ? WHERE id = ?" % table,
                     (clean, item_id))
        _audit(conn, uid, "rename", entity, item_id,
               before={"name": row["name"]}, after={"name": clean})
    return http_kit.json_response({"ok": True})


def _set_active_row(conn, table, item_id, active, uid, entity):
    row = conn.execute("SELECT * FROM %s WHERE id = ?" % table,
                       (item_id,)).fetchone()
    if row is None:
        raise ApiError(404, "not_found", S["err_not_found"])
    if active not in (0, 1):
        raise ApiError(400, "bad_active", S["err_invalid"])
    with conn:
        conn.execute("UPDATE %s SET active = ? WHERE id = ?" % table,
                     (active, item_id))
        _audit(conn, uid, "set_active", entity, item_id,
               before={"active": row["active"]}, after={"active": active})
    return http_kit.json_response({"ok": True})


def _active_flag(body):
    try:
        active = int(body.get("active"))
    except (TypeError, ValueError):
        raise ApiError(400, "bad_active", S["err_invalid"])
    if active not in (0, 1):
        raise ApiError(400, "bad_active", S["err_invalid"])
    return active


def api_rename_material(context, request, item_id):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        return _rename_row(conn, "materials", item_id, body.get("name"),
                           uid, "material")
    finally:
        conn.close()


def api_set_material_active(context, request, item_id):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        return _set_active_row(conn, "materials", item_id,
                               _active_flag(body), uid, "material")
    finally:
        conn.close()


def api_rename_product(context, request, item_id):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        return _rename_row(conn, "products", item_id, body.get("name"),
                           uid, "product")
    finally:
        conn.close()


def api_set_product_active(context, request, item_id):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        return _set_active_row(conn, "products", item_id,
                               _active_flag(body), uid, "product")
    finally:
        conn.close()


def api_material_detail(context, request, item_id):
    """One material with its units and full cost history (newest first)."""
    conn = context.connect()
    try:
        mat = conn.execute("SELECT * FROM materials WHERE id = ?",
                           (item_id,)).fetchone()
        if mat is None:
            raise ApiError(404, "not_found", S["err_not_found"])
        units = [{"id": u["id"], "unit_name": u["unit_name"],
                  "factor_to_base": u["factor_to_base"],
                  "is_base_unit": u["is_base_unit"]}
                 for u in db.units_for(conn, mat["id"])]
        costs = [{"id": r["id"], "unit_name": r["unit_name"],
                  "price_piasters": r["price_piasters"],
                  "effective_date": r["effective_date"]}
                 for r in conn.execute(
                     "SELECT mc.id, u.unit_name, mc.price_piasters,"
                     " mc.effective_date FROM material_costs mc"
                     " JOIN count_units u ON u.id = mc.count_unit_id"
                     " WHERE mc.material_id = ?"
                     " ORDER BY mc.effective_date DESC, mc.id DESC",
                     (mat["id"],))]
        return http_kit.json_response({
            "id": mat["id"], "name": mat["name"],
            "department": mat["department"], "base_unit": mat["base_unit"],
            "is_cup": bool(mat["is_cup"]), "active": mat["active"],
            "units": units, "costs": costs,
        })
    finally:
        conn.close()


def api_product_detail(context, request, item_id):
    """One product with price and recipe history (newest first)."""
    conn = context.connect()
    try:
        prod = conn.execute("SELECT * FROM products WHERE id = ?",
                            (item_id,)).fetchone()
        if prod is None:
            raise ApiError(404, "not_found", S["err_not_found"])
        prices = [{"id": r["id"], "price_piasters": r["price_piasters"],
                   "effective_date": r["effective_date"]}
                  for r in conn.execute(
                      "SELECT id, price_piasters, effective_date"
                      " FROM product_prices WHERE product_id = ?"
                      " ORDER BY effective_date DESC, id DESC",
                      (prod["id"],))]
        recipe = [{"id": r["id"], "material_id": r["material_id"],
                   "material_name": r["material_name"],
                   "qty_base": r["qty_base"],
                   "effective_date": r["effective_date"]}
                  for r in conn.execute(
                      "SELECT rl.id, rl.material_id, m.name AS material_name,"
                      " rl.qty_base, rl.effective_date FROM recipe_lines rl"
                      " JOIN materials m ON m.id = rl.material_id"
                      " WHERE rl.product_id = ?"
                      " ORDER BY rl.effective_date DESC, rl.id DESC",
                      (prod["id"],))]
        return http_kit.json_response({
            "id": prod["id"], "name": prod["name"],
            "department": prod["department"],
            "sold_source": prod["sold_source"],
            "source_material_id": prod["source_material_id"],
            "recipe_qty_base": prod["recipe_qty_base"],
            "coffee_material_id": prod["coffee_material_id"],
            "uses_cup": bool(prod["uses_cup"]), "active": prod["active"],
            "prices": prices, "recipe": recipe,
        })
    finally:
        conn.close()


def _egp(piasters):
    return "%d.%02d" % (piasters // 100, abs(piasters) % 100)


def api_export_csv(context, request):
    date_from = _date(request.query.get("from") or "")
    date_to = _date(request.query.get("to") or "")
    if date_to < date_from:
        raise ApiError(400, "bad_range", S["err_invalid"])
    conn = context.connect()
    try:
        lines_out = ["date,product,qty_sold,revenue_egp,cost_egp,profit_egp"]
        days = conn.execute(
            "SELECT business_date FROM business_days"
            " WHERE business_date BETWEEN ? AND ? ORDER BY business_date",
            (date_from, date_to)).fetchall()
        for day in days:
            rep = build_day_report(conn, day["business_date"])
            for line in rep["lines"]:
                name = line["name"].replace('"', '""')
                lines_out.append("%s,\"%s\",%d,%s,%s,%s" % (
                    day["business_date"], name, line["qty_sold"],
                    _egp(line["revenue"]), _egp(line["cost"]),
                    _egp(line["profit"])))
        body = "\n".join(lines_out) + "\n"
        # UTF-8 BOM so Excel on the Arabic-locale PC opens it correctly.
        raw = "\ufeff" + body
        return http_kit.Response(200, raw, "text/csv; charset=utf-8",
                                 [("Content-Disposition",
                                   "attachment; filename=kitchen_report.csv")])
    finally:
        conn.close()


def api_backup(context, request):
    body = _body(request)
    conn = context.connect()
    try:
        uid = _user_id(conn, body)
        path = db.backup_db(context.db_path)
        _audit(conn, uid, "backup", "database", after={"path": path})
        conn.commit()
        return http_kit.json_response({"ok": True, "path": path,
                                       "backups": _list_backups(context)})
    finally:
        conn.close()


def _list_backups(context):
    import glob as _glob
    base = os.path.dirname(os.path.abspath(context.db_path))
    folder = os.path.join(base, db.BACKUP_DIR_NAME)
    try:
        names = sorted(_glob.glob(os.path.join(folder, "kitchen_*.db")))
    except OSError:
        return []
    out = []
    for path in names[-30:]:
        try:
            stat = os.stat(path)
            out.append({"path": path,
                        "name": os.path.basename(path),
                        "size_bytes": stat.st_size,
                        "mtime": stat.st_mtime})
        except OSError:
            out.append({"path": path,
                        "name": os.path.basename(path),
                        "size_bytes": 0, "mtime": 0})
    return out


def api_list_backups(context, request):
    return http_kit.json_response({"backups": _list_backups(context)})
