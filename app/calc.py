# calc.py - PURE inventory and profit calculations for the kitchen/cafeteria app.
#
# This module does NO database access and NO HTTP. Every function takes plain
# numbers/strings/lists/dicts and returns plain values, so the whole business
# logic can be unit tested with unittest on any interpreter.
#
# Money convention: INTEGER piasters everywhere (1 EGP = 100 piasters).
# Quantity convention: INTEGER base units (g, ml or piece). Staff may enter
# fractional count units (e.g. 0.5 carton); the conversion rounds half UP to
# the nearest integer base unit (Python's round() is banker's rounding and
# would silently under-count every other half unit, so it is NOT used here).
#
# Standard library only, Python 3.8 compatible (no match, no X | Y types,
# no builtin generics in annotations, no removeprefix, no zoneinfo).

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Limits (server-side validation helpers use these; kept here so tests and
# routes share the exact same numbers).
# ---------------------------------------------------------------------------

# Largest single entered quantity (in the chosen count unit).
MAX_ENTERED_QTY = 100000.0
# Largest stored base quantity for one count/receipt row.
MAX_BASE_QTY = 100000000
# Largest money amount for one price field (100 million piasters = 1M EGP).
MAX_PRICE_PIASTERS = 100000000
# Largest sold quantity for one product on one day.
MAX_QTY_SOLD = 100000
# Spike warning: a count above this multiple of the 14-day average warns.
SPIKE_MULTIPLE = 10.0
# Coffee cross-check tolerances: warn when the manual plain-coffee count
# differs from the derived estimate by more than BOTH thresholds combined:
# tolerance = max(3 cups, 5% of the derived value).
COFFEE_CHECK_MIN_CUPS = 3
COFFEE_CHECK_PCT = 0.05
# Coffee yield confidence bands.
YIELD_HIGH_MIN_CUPS = 100
YIELD_HIGH_MIN_DAYS = 7
YIELD_MED_MIN_CUPS = 30
YIELD_MED_MIN_DAYS = 3


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

def to_base_qty(entered_qty, factor):
    # type: (float, int) -> int
    """Convert an entered count-unit quantity to integer base units.

    entered_qty may be fractional (0.5 carton). factor is the integer number
    of base units in one count unit (e.g. kg -> 1000 g). Rounds half UP.
    Raises ValueError on negative qty or non-positive factor.
    """
    if factor <= 0:
        raise ValueError("factor must be positive")
    if entered_qty < 0:
        raise ValueError("quantity must not be negative")
    # Half-up rounding without floats drifting: scale by 1000 first so that
    # common fractions (0.5, 0.25, 1.5) are exact.
    scaled = int(round(entered_qty * 1000.0))
    return (scaled * factor + 500) // 1000


def to_entered_qty(base_qty, factor):
    # type: (int, int) -> float
    """Convert integer base units back to count units (display only)."""
    if factor <= 0:
        raise ValueError("factor must be positive")
    return base_qty / float(factor)


# ---------------------------------------------------------------------------
# Consumption
# ---------------------------------------------------------------------------

def consumed(opening_base, received_base, closing_base):
    # type: (int, int, int) -> int
    """consumed = opening + received - closing (all integer base units)."""
    return opening_base + received_base - closing_base


def closing_needs_reason(opening_base, received_base, closing_base):
    # type: (int, int, int) -> bool
    """True when closing > opening + received: a blocking error unless the
    user confirms with a written reason (stored on the count row)."""
    return closing_base > opening_base + received_base


# ---------------------------------------------------------------------------
# Validation helpers (return an error string, or None when valid)
# ---------------------------------------------------------------------------

def check_base_qty(value, label="quantity"):
    # type: (int, str) -> Optional[str]
    if not isinstance(value, int):
        return "%s must be a whole number" % label
    if value < 0:
        return "%s must not be negative" % label
    if value > MAX_BASE_QTY:
        return "%s is unreasonably large" % label
    return None


def check_entered_qty(value, label="quantity"):
    # type: (float, str) -> Optional[str]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "%s must be a number" % label
    if number < 0:
        return "%s must not be negative" % label
    if number > MAX_ENTERED_QTY:
        return "%s is unreasonably large" % label
    return None


def check_price_piasters(value, label="price"):
    # type: (int, str) -> Optional[str]
    if not isinstance(value, int):
        return "%s must be a whole number of piasters" % label
    if value < 0:
        return "%s must not be negative" % label
    if value > MAX_PRICE_PIASTERS:
        return "%s is unreasonably large" % label
    return None


def check_qty_sold(value, label="sold quantity"):
    # type: (int, str) -> Optional[str]
    if not isinstance(value, int):
        return "%s must be a whole number" % label
    if value < 0:
        return "%s must not be negative" % label
    if value > MAX_QTY_SOLD:
        return "%s is unreasonably large" % label
    return None


def is_spike(count_base, avg14_base):
    # type: (int, float) -> bool
    """Warn when a count jumps above 10x of that material's 14-day average.
    An average of zero (new material) never warns - there is no baseline."""
    if avg14_base is None or avg14_base <= 0:
        return False
    return count_base > SPIKE_MULTIPLE * avg14_base


def valid_business_date(text):
    # type: (str) -> bool
    """Strict YYYY-MM-DD check (the business date is typed/chosen in the UI;
    the OS clock on this PC is wrong, so it is never trusted)."""
    if not isinstance(text, str) or len(text) != 10:
        return False
    if text[4] != "-" or text[7] != "-":
        return False
    try:
        year = int(text[0:4])
        month = int(text[5:7])
        day = int(text[8:10])
    except ValueError:
        return False
    if month < 1 or month > 12 or day < 1 or day > 31:
        return False
    if month in (4, 6, 9, 11) and day > 30:
        return False
    if month == 2:
        leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
        if day > (29 if leap else 28):
            return False
    return True


# ---------------------------------------------------------------------------
# Effective-dated lookup (prices, costs, recipes)
# ---------------------------------------------------------------------------

def effective_lookup(rows, business_date):
    # type: (List[Tuple[str, Any]], str) -> Any
    """Return the value of the latest row with effective_date <= business_date.

    rows is a list of (effective_date, value) with dates as YYYY-MM-DD
    strings (lexicographic comparison is chronological for this format).
    Returns None when no row is effective yet. Past days never change when
    prices/recipes change because every lookup is pinned to the day.
    """
    best_date = None
    best_value = None
    for eff_date, value in rows:
        if eff_date <= business_date:
            if best_date is None or eff_date >= best_date:
                best_date = eff_date
                best_value = value
    return best_value


# ---------------------------------------------------------------------------
# Sold-quantity rules
# ---------------------------------------------------------------------------

def sachet_cups(consumed_base, recipe_qty_base):
    # type: (int, int) -> Tuple[int, int]
    """derived_from_material: 1 sachet = 1 cup. Returns (cups, remainder_base).

    cups = consumed // recipe_qty; any remainder stays visible so a torn
    sachet or miscount is not silently swallowed.
    """
    if recipe_qty_base <= 0:
        raise ValueError("recipe quantity must be positive")
    if consumed_base < 0:
        raise ValueError("consumed must not be negative")
    return consumed_base // recipe_qty_base, consumed_base % recipe_qty_base


def remainder_coffee_cups(cups_consumed, other_cups_total):
    # type: (int, int) -> Tuple[int, bool]
    """derived_remainder_of_cup: coffee cups = packaging cups consumed minus
    the cups of every other drink using the packaging cup. Returns
    (coffee_cups, negative_flag): a negative pool is clamped to 0 and flagged
    so the UI shows a warning instead of a nonsense negative sale."""
    pool = cups_consumed - other_cups_total
    if pool < 0:
        return 0, True
    return pool, False


def coffee_crosscheck(derived_cups, counted_cups):
    # type: (int, int) -> Tuple[bool, int]
    """Cross-check the optional manual plain-coffee count against the derived
    estimate. Returns (ok, tolerance): ok is False when the absolute
    difference is strictly greater than max(3 cups, 5% of derived)."""
    tolerance = int(COFFEE_CHECK_MIN_CUPS)
    pct_part = int(derived_cups * COFFEE_CHECK_PCT)
    if pct_part > tolerance:
        tolerance = pct_part
    return abs(counted_cups - derived_cups) <= tolerance, tolerance


# ---------------------------------------------------------------------------
# Coffee yield (user NEVER types grams per cup)
# ---------------------------------------------------------------------------

def coffee_yield(daily_pairs, bag_size_base, fallback_gpc):
    # type: (List[Tuple[int, int]], int, float) -> Dict[str, Any]
    """grams_per_cup = coffee grams consumed / coffee cups sold over the
    period. daily_pairs is [(grams_base, cups_sold)] per day (only days with
    cups_sold > 0 contribute). cups_per_bag = bag size / grams per cup.

    Fallback chain: period -> caller passes a wider period (or all history)
    -> fallback_gpc (initial manual estimate). Confidence uses days+cups used:
    high (>=7 days and >=100 cups), medium (>=3 days and >=30 cups),
    else low; the estimate fallback reports 'none'.
    """
    grams = 0
    cups = 0
    days = 0
    for grams_day, cups_day in daily_pairs:
        if cups_day > 0:
            grams += grams_day
            cups += cups_day
            days += 1
    if cups <= 0 or grams <= 0:
        return {
            "grams_per_cup": float(fallback_gpc),
            "cups_per_bag": (bag_size_base / float(fallback_gpc)
                             if fallback_gpc > 0 else 0.0),
            "days_used": 0,
            "cups_used": 0,
            "confidence": "none",
            "source": "estimate",
        }
    gpc = grams / float(cups)
    if days >= YIELD_HIGH_MIN_DAYS and cups >= YIELD_HIGH_MIN_CUPS:
        confidence = "high"
    elif days >= YIELD_MED_MIN_DAYS and cups >= YIELD_MED_MIN_CUPS:
        confidence = "medium"
    else:
        confidence = "low"
    return {
        "grams_per_cup": gpc,
        "cups_per_bag": bag_size_base / gpc if gpc > 0 else 0.0,
        "days_used": days,
        "cups_used": cups,
        "confidence": confidence,
        "source": "measured",
    }


# ---------------------------------------------------------------------------
# Money input: staff type EGP (never piasters)
# ---------------------------------------------------------------------------

def egp_to_piasters(value):
    # type: (object) -> int
    """Convert an EGP amount (string or number, up to 2 decimals) to integer
    piasters. The conversion is exact; more than 2 decimals, negatives,
    NaN/inf and non-numeric input raise ValueError (the API turns it into a
    400 response)."""
    if isinstance(value, bool):
        raise ValueError("amount must be a number")
    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("amount is not a number")
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("amount is empty")
    else:
        raise ValueError("amount must be a number")
    neg = False
    if text[:1] in ("+", "-"):
        neg = text[:1] == "-"
        text = text[1:]
    if not text or text.count(".") > 1 or \
            not text.replace(".", "", 1).isdigit():
        raise ValueError("amount is not a number")
    whole, _, frac = text.partition(".")
    if len(frac) > 2:
        raise ValueError("at most 2 decimals allowed")
    piasters = int(whole or "0") * 100 + int((frac + "00")[:2])
    if neg:
        raise ValueError("amount must not be negative")
    return piasters


# ---------------------------------------------------------------------------
# Money: cost, revenue, profit, variance (integer piasters, half-up rounding)
# ---------------------------------------------------------------------------

def cost_piasters(qty_base, unit_price_piasters, factor):
    # type: (int, int, int) -> int
    """Cost of qty_base base units when one count unit (factor base units)
    costs unit_price_piasters. Exact integer arithmetic, halves round up."""
    if factor <= 0:
        raise ValueError("factor must be positive")
    if qty_base < 0:
        raise ValueError("quantity must not be negative")
    if qty_base == 0 or unit_price_piasters == 0:
        return 0
    return (2 * qty_base * unit_price_piasters + factor) // (2 * factor)


def revenue_piasters(qty_sold, price_piasters):
    # type: (int, int) -> int
    return qty_sold * price_piasters


def profit_piasters(revenue, cost):
    # type: (int, int) -> int
    return revenue - cost


def usage_variance(actual_consumed_base, expected_base):
    # type: (int, int) -> int
    """actual - expected in base units (positive = used more than recipe)."""
    return actual_consumed_base - expected_base


# ---------------------------------------------------------------------------
# Day summary (pure assembler used by the report endpoint AND the tests)
# ---------------------------------------------------------------------------
#
# products:    [{id, name, sold_source, source_material_id (or None),
#                recipe_qty_base (per-cup qty for derived_from_material),
#                uses_cup (bool), coffee_material_id (or None, for remainder
#                products whose cost uses the measured yield),
#                recipe: [{material_id, qty_base}]}]
# consumed:    {material_id: base_qty consumed that day}
# prices:      {product_id: price_piasters effective that day}
# unit_costs:  {material_id: (price_piasters, factor) effective that day}
# cups_consumed: packaging cups consumed that day (int base units = pieces)
# manual_sales:  {product_id: qty_sold} for sold_source == 'manual'
# coffee_gpc:    measured grams per cup (None -> remainder coffee cost is 0
#                and a warning is emitted; the owner must fix the yield)
# material_names: optional {material_id: name} used to label the "variance"
#                per-material list.
#
# Returns lines (per-dish variance_base/variance_egp only for materials that
# dish uses alone), variance (one entry per material used by manual dishes:
# actual vs summed expected, in base units and piasters, with dish names),
# cups_by_drink + total_cups, reconciliation and warnings.
#
# ASSUMPTION (documented): a remainder-source (coffee) product's cost is the
# MEASURED coffee cost (cups x grams-per-cup x effective cost per gram) PLUS
# every OTHER recipe line (packaging cup, milk, sugar, ...) x cups. The
# coffee material's own recipe line, if present, is always skipped so the
# measured coffee is never double counted. All other products cost recipe
# qty x unit cost.
# material_names: optional {material_id: name} for the variance list labels.

def compute_day_summary(products, consumed, prices, unit_costs, cups_consumed,
                        manual_sales=None, coffee_gpc=None,
                        material_names=None):
    # type: (List[Dict[str, Any]], Dict[int, int], Dict[int, int], Dict[int, Tuple[int, int]], int, Optional[Dict[int, int]], Optional[float], Optional[Dict[int, str]]) -> Dict[str, Any]
    manual_sales = manual_sales or {}
    material_names = material_names or {}
    lines = []  # type: List[Dict[str, Any]]
    warnings = []  # type: List[str]
    total_revenue = 0
    total_cost = 0
    total_cups = 0
    cups_by_drink = []  # type: List[Dict[str, Any]]

    # A day still being entered can show negative consumption (a closing was
    # typed before its receipts). Clamp to 0 with a warning instead of
    # crashing: the report is a live preview until the day is closed.
    consumed = dict(consumed)
    for mat_id in sorted(consumed):
        if consumed[mat_id] < 0:
            warnings.append("negative consumption %d for material %s; "
                            "treated as 0 until the day is complete"
                            % (consumed[mat_id], mat_id))
            consumed[mat_id] = 0

    # First pass: sachet-derived and manual products (need their cups before
    # the coffee remainder can be computed).
    derived_cups = {}  # type: Dict[int, int]
    remainder_products = []
    for product in products:
        source = product.get("sold_source")
        if source == "derived_from_material":
            mat_id = product.get("source_material_id")
            per_cup = product.get("recipe_qty_base") or 0
            cups, rem = sachet_cups(consumed.get(mat_id, 0), per_cup)
            if rem:
                warnings.append("remainder %d base units of material %s "
                                "unaccounted for %s" % (rem, mat_id,
                                                        product.get("name")))
            derived_cups[product["id"]] = cups
        elif source == "derived_remainder_of_cup":
            remainder_products.append(product)

    other_cups = sum(cups for pid, cups in derived_cups.items()
                     if _product_uses_cup(products, pid))
    coffee_cups, negative_pool = remainder_coffee_cups(cups_consumed,
                                                      other_cups)
    if negative_pool:
        warnings.append("packaging cups consumed (%d) below sum of derived "
                        "drink cups (%d)" % (cups_consumed, other_cups))
    if len(remainder_products) > 1:
        warnings.append("multiple remainder (coffee) products configured; "
                        "pool assigned to none")
        coffee_each = 0
    else:
        coffee_each = coffee_cups

    for product in products:
        pid = product["id"]
        name = product.get("name", "")
        source = product.get("sold_source")
        price = prices.get(pid, 0)
        if source == "derived_from_material":
            qty = derived_cups.get(pid, 0)
            method = "derived_from_material"
        elif source == "derived_remainder_of_cup":
            if len(remainder_products) > 1:
                qty = 0
            else:
                qty = coffee_each
            method = "derived_remainder_of_cup"
        elif source == "manual":
            qty = manual_sales.get(pid, 0)
            method = "manual"
        else:
            warnings.append("unknown sold_source for %s" % name)
            continue

        revenue = revenue_piasters(qty, price)
        cost = 0
        if source == "derived_remainder_of_cup":
            coffee_mid = product.get("coffee_material_id")
            if qty:
                if coffee_mid is not None and coffee_gpc is not None:
                    unit = unit_costs.get(coffee_mid)
                    if unit is not None:
                        # Measured coffee part, integer arithmetic on
                        # milli-grams, halves round up.
                        unit_price, factor = unit
                        milli_grams = int(round(qty * coffee_gpc * 1000.0))
                        cost += (2 * milli_grams * unit_price
                                 + factor * 1000) // (2 * factor * 1000)
                    else:
                        warnings.append(
                            "no effective cost for coffee material on %s"
                            % name)
                elif coffee_mid is None or coffee_gpc is None:
                    warnings.append("coffee yield unavailable; coffee part "
                                    "of %s cost set to 0" % name)
                # Every OTHER recipe line (cup, milk, sugar, ...) x cups.
                # The coffee material's own line is skipped: it is already
                # priced by the measured yield above.
                for line in product.get("recipe", []):
                    mat_id = line.get("material_id")
                    if mat_id == coffee_mid:
                        continue
                    need = qty * line.get("qty_base", 0)
                    unit = unit_costs.get(mat_id)
                    if unit is None:
                        warnings.append(
                            "no effective cost for material %s in %s"
                            % (mat_id, name))
                        continue
                    unit_price, factor = unit
                    cost += cost_piasters(need, unit_price, factor)
        else:
            for line in product.get("recipe", []):
                mat_id = line.get("material_id")
                need = qty * line.get("qty_base", 0)
                unit = unit_costs.get(mat_id)
                if unit is None:
                    warnings.append("no effective cost for material %s in "
                                    "%s" % (mat_id, name))
                    continue
                unit_price, factor = unit
                cost += cost_piasters(need, unit_price, factor)

        profit = profit_piasters(revenue, cost)
        total_revenue += revenue
        total_cost += cost
        if product.get("uses_cup"):
            total_cups += qty
            cups_by_drink.append({"product_id": pid, "name": name,
                                  "cups": qty})
        line = {"product_id": pid, "name": name, "qty_sold": qty,
                "method": method, "revenue": revenue, "cost": cost,
                "profit": profit}
        lines.append(line)

    # Dish variance, computed ONCE per material per day: actual consumed minus
    # the sum of (sold x recipe qty) over ALL manual products. Per-dish
    # variance fields are attached only for materials that dish uses alone;
    # shared materials live only in the per-material list below.
    manual_products = [p for p in products
                       if p.get("sold_source") == "manual"]
    users_of = {}  # type: Dict[int, List[int]]
    for product in manual_products:
        for line in product.get("recipe", []):
            users_of.setdefault(line.get("material_id"), []).append(
                product["id"])
    variance = []  # type: List[Dict[str, Any]]
    exclusive_expected = {}  # type: Dict[int, Dict[int, int]]
    for mat_id, user_ids in users_of.items():
        expected_total = 0
        dishes = []
        for product in manual_products:
            if product["id"] not in user_ids:
                continue
            qty = manual_sales.get(product["id"], 0)
            for line in product.get("recipe", []):
                if line.get("material_id") == mat_id:
                    expected_total += qty * line.get("qty_base", 0)
            dishes.append(product.get("name", ""))
        actual = consumed.get(mat_id, 0)
        var = usage_variance(actual, expected_total)
        var_egp = 0
        unit = unit_costs.get(mat_id)
        if unit is None:
            warnings.append("no effective cost for variance of material %s"
                            % mat_id)
        else:
            unit_price, factor = unit
            var_egp = cost_piasters(abs(var), unit_price, factor) * (
                1 if var >= 0 else -1)
        variance.append({"material_id": mat_id,
                         "material_name": material_names.get(mat_id),
                         "actual_base": actual,
                         "expected_base": expected_total,
                         "variance_base": var,
                         "variance_piasters": var_egp,
                         "dishes": dishes})
        if len(user_ids) == 1:
            exclusive_expected.setdefault(user_ids[0], {})[mat_id] = (
                expected_total)
    for line in lines:
        pid = line["product_id"]
        exclusive = exclusive_expected.get(pid)
        if not exclusive:
            continue
        dish_var = 0
        dish_var_egp = 0
        for mat_id, expected in exclusive.items():
            actual = consumed.get(mat_id, 0)
            var = usage_variance(actual, expected)
            dish_var += var
            unit = unit_costs.get(mat_id)
            if unit is not None:
                unit_price, factor = unit
                dish_var_egp += cost_piasters(
                    abs(var), unit_price, factor) * (1 if var >= 0 else -1)
        line["variance_base"] = dish_var
        line["variance_egp"] = dish_var_egp

    reconciliation = {
        "cups_consumed": cups_consumed,
        "cups_derived_total": total_cups,
        "difference": cups_consumed - total_cups,
    }
    if reconciliation["difference"] != 0:
        warnings.append("cup reconciliation differs by %d" %
                        reconciliation["difference"])
    return {"lines": lines, "total_revenue": total_revenue,
            "total_cost": total_cost,
            "total_profit": profit_piasters(total_revenue, total_cost),
            "cups_by_drink": cups_by_drink, "total_cups": total_cups,
            "variance": variance,
            "reconciliation": reconciliation, "warnings": warnings}


def _product_uses_cup(products, product_id):
    # type: (List[Dict[str, Any]], int) -> bool
    for product in products:
        if product.get("id") == product_id:
            return bool(product.get("uses_cup"))
    return False
