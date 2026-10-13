# test_calc.py - unit tests for app/calc.py (pure functions only).
#
# Run from the repository root:
#     python -m unittest discover -s tests -v
# or directly:  python tests/test_calc.py
# Target check:  runtime\python.exe -m unittest discover -s tests
# Standard library only (unittest), Python 3.8 compatible.

import os
import sys
import unittest

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_DIR = os.path.join(_ROOT_DIR, "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import calc  # noqa: E402


class TestUnitConversion(unittest.TestCase):

    def test_kg_to_grams(self):
        self.assertEqual(calc.to_base_qty(2.0, 1000), 2000)

    def test_fraction_carton(self):
        # 0.5 carton of 24 pieces = 12 pieces.
        self.assertEqual(calc.to_base_qty(0.5, 24), 12)

    def test_quarter_box(self):
        # 1.25 boxes of 20 sachets = 25 sachets.
        self.assertEqual(calc.to_base_qty(1.25, 20), 25)

    def test_half_up_not_bankers(self):
        # 0.5 g with factor 1 must round UP to 1, not to 0 (banker's).
        self.assertEqual(calc.to_base_qty(0.5, 1), 1)
        # 2.5 -> 3, not 2.
        self.assertEqual(calc.to_base_qty(2.5, 1), 3)

    def test_zero(self):
        self.assertEqual(calc.to_base_qty(0.0, 1000), 0)

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            calc.to_base_qty(-1.0, 1000)

    def test_bad_factor_rejected(self):
        with self.assertRaises(ValueError):
            calc.to_base_qty(1.0, 0)

    def test_round_trip_display(self):
        self.assertAlmostEqual(calc.to_entered_qty(1500, 1000), 1.5)


class TestConsumption(unittest.TestCase):

    def test_basic(self):
        self.assertEqual(calc.consumed(1000, 500, 900), 600)

    def test_zero_movement(self):
        self.assertEqual(calc.consumed(100, 0, 100), 0)

    def test_negative_close_flagged(self):
        # closing above opening + received needs a written reason.
        self.assertTrue(calc.closing_needs_reason(100, 50, 200))
        self.assertFalse(calc.closing_needs_reason(100, 50, 150))
        self.assertFalse(calc.closing_needs_reason(100, 50, 0))


class TestSachetRule(unittest.TestCase):

    def test_one_sachet_one_cup(self):
        cups, rem = calc.sachet_cups(47, 1)
        self.assertEqual((cups, rem), (47, 0))

    def test_remainder_reported(self):
        cups, rem = calc.sachet_cups(47, 2)
        self.assertEqual((cups, rem), (23, 1))

    def test_zero_consumed(self):
        self.assertEqual(calc.sachet_cups(0, 1), (0, 0))


class TestRemainderRule(unittest.TestCase):

    def test_coffee_pool(self):
        # 100 cups consumed, 30 tea + 10 anise + 5 hibiscus + 5 mint = 50.
        cups, neg = calc.remainder_coffee_cups(100, 50)
        self.assertEqual((cups, neg), (50, False))

    def test_all_kinds_subtracted(self):
        cups, neg = calc.remainder_coffee_cups(80, 80)
        self.assertEqual((cups, neg), (0, False))

    def test_negative_pool_clamped(self):
        cups, neg = calc.remainder_coffee_cups(40, 50)
        self.assertEqual((cups, neg), (0, True))

    def test_crosscheck_within_tolerance(self):
        ok, _tol = calc.coffee_crosscheck(100, 102)
        self.assertTrue(ok)

    def test_crosscheck_outside_percent(self):
        ok, tol = calc.coffee_crosscheck(100, 110)
        self.assertFalse(ok)
        self.assertEqual(tol, 5)  # max(3, 5% of 100)

    def test_crosscheck_minimum_three_cups(self):
        # Small shop: 5% of 20 is 1, floor is 3 cups.
        ok, tol = calc.coffee_crosscheck(20, 23)
        self.assertTrue(ok)
        self.assertEqual(tol, 3)
        ok2, _ = calc.coffee_crosscheck(20, 24)
        self.assertFalse(ok2)


class TestYield(unittest.TestCase):

    def test_measured_yield(self):
        # 3000 g over 300 cups over 10 days -> 10 g/cup.
        pairs = [(300, 30)] * 10
        result = calc.coffee_yield(pairs, 250, 8.0)
        self.assertAlmostEqual(result["grams_per_cup"], 10.0)
        self.assertAlmostEqual(result["cups_per_bag"], 25.0)
        self.assertEqual(result["days_used"], 10)
        self.assertEqual(result["cups_used"], 300)
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["source"], "measured")

    def test_low_confidence(self):
        result = calc.coffee_yield([(20, 2)], 250, 8.0)
        self.assertEqual(result["confidence"], "low")

    def test_fallback_estimate(self):
        result = calc.coffee_yield([], 250, 8.0)
        self.assertAlmostEqual(result["grams_per_cup"], 8.0)
        self.assertAlmostEqual(result["cups_per_bag"], 31.25)
        self.assertEqual(result["confidence"], "none")
        self.assertEqual(result["source"], "estimate")

    def test_zero_cup_days_ignored(self):
        result = calc.coffee_yield([(0, 0), (100, 10)], 250, 8.0)
        self.assertEqual(result["days_used"], 1)
        self.assertAlmostEqual(result["grams_per_cup"], 10.0)


class TestEffectiveLookup(unittest.TestCase):

    def test_picks_latest_effective(self):
        rows = [("2026-01-01", 1000), ("2026-02-01", 1500)]
        self.assertEqual(calc.effective_lookup(rows, "2026-01-15"), 1000)
        self.assertEqual(calc.effective_lookup(rows, "2026-03-01"), 1500)

    def test_none_before_first(self):
        self.assertIsNone(calc.effective_lookup([("2026-02-01", 5)], "2026-01-01"))

    def test_past_day_frozen(self):
        # A price change tomorrow must not rewrite yesterday's lookup.
        rows = [("2026-01-01", 1000), ("2026-02-01", 1500)]
        self.assertEqual(calc.effective_lookup(rows, "2026-01-20"), 1000)


class TestMoney(unittest.TestCase):

    def test_cost_exact(self):
        # 2 cups x 1 sachet at 100 piasters per sachet (factor 1).
        self.assertEqual(calc.cost_piasters(2, 100, 1), 200)

    def test_cost_rounds_half_up(self):
        # 1 g of coffee at 3000 piasters/kg -> 3 piasters exactly.
        self.assertEqual(calc.cost_piasters(1, 3000, 1000), 3)
        # 1 base @ 1500/1000 = 1.5 -> 2.
        self.assertEqual(calc.cost_piasters(1, 1500, 1000), 2)

    def test_profit(self):
        self.assertEqual(calc.profit_piasters(1500, 400), 1100)

    def test_variance(self):
        self.assertEqual(calc.usage_variance(1200, 1000), 200)
        self.assertEqual(calc.usage_variance(800, 1000), -200)


class TestEgpInput(unittest.TestCase):

    def test_whole(self):
        self.assertEqual(calc.egp_to_piasters("15"), 1500)
        self.assertEqual(calc.egp_to_piasters(15), 1500)
        self.assertEqual(calc.egp_to_piasters(15.0), 1500)

    def test_decimals(self):
        self.assertEqual(calc.egp_to_piasters("15.50"), 1550)
        self.assertEqual(calc.egp_to_piasters(15.5), 1550)
        self.assertEqual(calc.egp_to_piasters("0.99"), 99)
        self.assertEqual(calc.egp_to_piasters(" 7.25 "), 725)

    def test_rejected(self):
        for bad in ("10.123", "-5", "-0.01", "abc", "", "  ",
                    "1.2.3", None, True, float("nan"), float("inf"),
                    10.001, [15]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                calc.egp_to_piasters(bad)


class TestCoffeeRecipeCost(unittest.TestCase):

    def _products(self):
        return [
            {"id": 1, "name": "tea", "sold_source": "derived_from_material",
             "source_material_id": 11, "recipe_qty_base": 1, "uses_cup": True,
             "recipe": [{"material_id": 11, "qty_base": 1},
                        {"material_id": 10, "qty_base": 1}]},
            {"id": 2, "name": "coffee",
             "sold_source": "derived_remainder_of_cup",
             "coffee_material_id": 12, "uses_cup": True,
             "recipe": [{"material_id": 12, "qty_base": 5},
                        {"material_id": 10, "qty_base": 1},
                        {"material_id": 14, "qty_base": 8}]},
        ]

    def _run(self, cup_price):
        products = self._products()
        consumed = {10: 50, 11: 30, 12: 200, 14: 160}
        prices = {1: 1500, 2: 1500}
        unit_costs = {10: (cup_price, 1), 11: (100, 1), 12: (3000, 1000),
                      14: (500, 1000)}
        return calc.compute_day_summary(
            products, consumed, prices, unit_costs, cups_consumed=50,
            manual_sales={}, coffee_gpc=10.0)

    def test_other_lines_included_coffee_line_skipped(self):
        out = self._run(80)
        coffee = {ln["product_id"]: ln for ln in out["lines"]}[2]
        # 20 coffee cups: measured 20*10g @3000/1000 = 600, cup 20*1*80 =
        # 1600, milk 20*8g @500/1000 = 80. The coffee-material recipe line
        # (5 g) is skipped, not double counted.
        self.assertEqual(coffee["qty_sold"], 20)
        self.assertEqual(coffee["cost"], 600 + 1600 + 80)

    def test_cup_price_moves_coffee_profit(self):
        cheap = {ln["product_id"]: ln
                 for ln in self._run(80)["lines"]}[2]
        dear = {ln["product_id"]: ln
                for ln in self._run(100)["lines"]}[2]
        self.assertEqual(cheap["profit"] - dear["profit"], 20 * 20)


class TestSharedVariance(unittest.TestCase):

    def test_chicken_shared_by_two_dishes(self):
        products = [
            {"id": 1, "name": "chicken plate",
             "sold_source": "manual", "uses_cup": False,
             "recipe": [{"material_id": 21, "qty_base": 250}]},
            {"id": 2, "name": "chicken sandwich",
             "sold_source": "manual", "uses_cup": False,
             "recipe": [{"material_id": 21, "qty_base": 150}]},
            {"id": 3, "name": "potato plate",
             "sold_source": "manual", "uses_cup": False,
             "recipe": [{"material_id": 22, "qty_base": 200}]},
        ]
        # Sold 4 plates + 2 sandwiches: expected chicken = 4*250 + 2*150.
        consumed = {21: 1400, 22: 600}
        out = calc.compute_day_summary(
            products, consumed, {1: 6000, 2: 3000, 3: 2500},
            {21: (12000, 1000), 22: (2000, 1000)}, cups_consumed=0,
            manual_sales={1: 4, 2: 2, 3: 3},
            material_names={21: "chicken", 22: "potato"})
        by_id = {ln["product_id"]: ln for ln in out["lines"]}
        # Per-material list: chicken actual 1400 vs expected 1300.
        var = {v["material_id"]: v for v in out["variance"]}
        self.assertEqual(var[21]["variance_base"], 100)
        self.assertEqual(var[21]["expected_base"], 1300)
        self.assertEqual(var[21]["actual_base"], 1400)
        self.assertEqual(sorted(var[21]["dishes"]),
                         ["chicken plate", "chicken sandwich"])
        self.assertEqual(var[21]["material_name"], "chicken")
        # 100 g @ 12000/1000 = 1200 piasters over.
        self.assertEqual(var[21]["variance_piasters"], 1200)
        # Shared material appears on NO dish line...
        self.assertNotIn("variance_base", by_id[1])
        self.assertNotIn("variance_base", by_id[2])
        # ...while the exclusive potato variance stays on its dish.
        self.assertEqual(by_id[3]["variance_base"], 0)
        self.assertEqual(var[22]["variance_base"], 0)


class TestSpikeAndValidation(unittest.TestCase):

    def test_spike(self):
        self.assertTrue(calc.is_spike(101, 10.0))
        self.assertFalse(calc.is_spike(100, 10.0))
        self.assertFalse(calc.is_spike(5000, 0))  # new material: no warning

    def test_negative_rejected(self):
        self.assertIsNotNone(calc.check_base_qty(-1))
        self.assertIsNone(calc.check_base_qty(0))

    def test_business_date(self):
        self.assertTrue(calc.valid_business_date("2026-10-13"))
        self.assertFalse(calc.valid_business_date("2026-13-01"))
        self.assertFalse(calc.valid_business_date("13/10/2026"))
        self.assertFalse(calc.valid_business_date("2026-02-30"))


def _demo_products():
    # Tea (sachet), coffee (remainder), potato plate (manual).
    return [
        {"id": 1, "name": "tea", "sold_source": "derived_from_material",
         "source_material_id": 11, "recipe_qty_base": 1, "uses_cup": True,
         "recipe": [{"material_id": 11, "qty_base": 1},
                    {"material_id": 10, "qty_base": 1}]},
        {"id": 2, "name": "coffee", "sold_source": "derived_remainder_of_cup",
         "coffee_material_id": 12, "uses_cup": True, "recipe": []},
        {"id": 3, "name": "potato", "sold_source": "manual",
         "uses_cup": False,
         "recipe": [{"material_id": 13, "qty_base": 200}]},
    ]


class TestDaySummary(unittest.TestCase):

    def test_negative_consumption_clamped(self):
        # A day still being entered: closing typed before receipts gives a
        # negative consumption; the summary clamps to 0 with a warning
        # instead of raising.
        products = [
            {"id": 1, "name": "tea", "sold_source": "derived_from_material",
             "source_material_id": 11, "recipe_qty_base": 1, "uses_cup": True,
             "recipe": [{"material_id": 11, "qty_base": 1}]},
        ]
        out = calc.compute_day_summary(
            products, {11: -9}, {1: 1500}, {11: (100, 1)}, cups_consumed=0,
            manual_sales={})
        self.assertEqual(out["lines"][0]["qty_sold"], 0)
        self.assertEqual(out["lines"][0]["cost"], 0)
        self.assertTrue(any("negative consumption" in w
                            for w in out["warnings"]))

    def test_full_day(self):
        products = _demo_products()
        consumed = {10: 50, 11: 30, 12: 200, 13: 1000}
        prices = {1: 1500, 2: 1500, 3: 2000}
        unit_costs = {10: (50, 1), 11: (100, 1), 12: (3000, 1000),
                      13: (2000, 1000)}
        out = calc.compute_day_summary(
            products, consumed, prices, unit_costs, cups_consumed=50,
            manual_sales={3: 5}, coffee_gpc=10.0)
        by_id = {line["product_id"]: line for line in out["lines"]}
        # Tea: 30 sachets -> 30 cups; revenue 30*1500.
        self.assertEqual(by_id[1]["qty_sold"], 30)
        self.assertEqual(by_id[1]["revenue"], 45000)
        # Cups: 50 consumed - 30 tea = 20 coffee.
        self.assertEqual(by_id[2]["qty_sold"], 20)
        self.assertEqual(by_id[2]["revenue"], 30000)
        # Coffee cost: 20 cups * 10 g * 3000/1000 = 600 piasters.
        self.assertEqual(by_id[2]["cost"], 600)
        # Potato: 5 sold x 2000 = 10000 revenue.
        self.assertEqual(by_id[3]["revenue"], 10000)
        # Reconciliation: 50 consumed vs 30+20 derived.
        self.assertEqual(out["reconciliation"]["difference"], 0)
        self.assertEqual(out["total_revenue"], 85000)
        self.assertEqual(out["total_profit"],
                         out["total_revenue"] - out["total_cost"])
        # Explicit drink cups + per-material variance list.
        self.assertEqual(out["total_cups"], 50)
        self.assertEqual({d["name"]: d["cups"]
                          for d in out["cups_by_drink"]},
                         {"tea": 30, "coffee": 20})
        var = {v["material_id"]: v for v in out["variance"]}
        self.assertEqual(var[13]["variance_base"], 0)  # potato, exclusive
        self.assertEqual(by_id[3]["variance_base"], 0)

    def test_reconciliation_warns(self):
        products = _demo_products()
        out = calc.compute_day_summary(
            products, {10: 50, 11: 30}, {1: 1500, 2: 1500, 3: 2000},
            {10: (50, 1), 11: (100, 1)}, cups_consumed=55,
            manual_sales={}, coffee_gpc=10.0)
        # 55 cups consumed, 30 tea + 25 coffee = 55 -> no difference.
        self.assertEqual(out["reconciliation"]["difference"], 0)


if __name__ == "__main__":
    unittest.main()
