"""Real frozen-pipeline integration checks; local only, no credentials."""
import json
import os
import posixpath
import yaml
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest

from dynamic_pricing_app.runtime import PricingRuntime


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ.get("PRICING_TEST_PAYLOAD", "build/phase4-private"))
        cls.runtime = PricingRuntime.load(cls.root)
        cls.example = cls.runtime.lookup(limit=1)[0]

    def score(self, **kwargs):
        row = self.example
        return self.runtime.recommend(row["product_id"], row["store_id"], row["channel"], **kwargs)

    def test_business_output_and_cache_isolation(self):
        result = self.score()
        self.assertTrue(result["review_required"])
        self.assertIsNotNone(result["expected_gross_profit"])
        self.assertNotIn("CustomerID", json.dumps(result))
        self.assertNotIn("CostPrice", json.dumps(result))
        result["suggested_price"] = -1
        self.assertGreater(self.score()["suggested_price"], 0)

    def test_simulation_is_not_a_price_write(self):
        baseline = self.score()
        simulated = self.score(candidate_price=baseline["current_price"])
        self.assertEqual(simulated["suggested_price"], baseline["suggested_price"])
        self.assertEqual(simulated["simulation"]["candidate_price"], baseline["current_price"])
        self.assertTrue(simulated["simulation"]["review_required"])

    def test_invalid_inputs(self):
        for candidate in (True, -1, float("nan"), float("inf"), 1000000):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.score(candidate_price=candidate)
        with self.assertRaises(ValueError):
            self.score(as_of="2026-09-16")

    def test_five_concurrent_reads(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: self.score(), range(5)))
        self.assertEqual(len(results), 5)
        self.assertEqual(len({r["suggested_price"] for r in results}), 1)

    def test_private_projection(self):
        manifest = json.loads((self.root / "pricing-manifest.json").read_text())
        self.assertEqual(manifest["contexts"], 10500)
        self.assertTrue(manifest["advisory_only"])
        self.assertFalse({"CustomerID", "SessionID", "PurchasedFlag", "LoyaltyTier"}.intersection(manifest["feature_columns"]))

    def test_linux_entry_point_is_portable(self):
        metadata = yaml.safe_load((self.root / "model/MLmodel").read_text())
        entry = metadata["flavors"]["python_function"]["model_code_path"]
        self.assertEqual(posixpath.basename(entry), "phase3_model.py")
        self.assertEqual(entry, "phase3_model.py")
        manifest = json.loads((self.root / "pricing-manifest.json").read_text())
        self.assertEqual(manifest["packaging_adaptation"]["kind"], "PORTABLE_MODEL_CODE_PATH_ONLY")


if __name__ == "__main__":
    unittest.main()
