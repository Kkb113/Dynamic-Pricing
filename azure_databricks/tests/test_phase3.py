import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "azure_databricks/scripts"))
import pandas as pd
import phase3
from pricing_mlflow.pipeline import PricingPipeline, VERSION


class PricingServingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "build").mkdir(exist_ok=True)
        cls.pipeline = PricingPipeline(ROOT)
        cls.input = phase3.example(cls.pipeline)
        cls.payload = json.loads(cls.input.request_json.iloc[0])

    def test_advisory_frozen_model(self):
        result = self.pipeline.score(self.payload)
        self.assertTrue(result["advisory_only"])
        self.assertFalse(result["auto_writeback"])
        row = result["decisions"][0]
        self.assertGreater(row["raw_purchase_probability"], 0)
        self.assertLessEqual(row["expected_units"], row["raw_expected_units"] + 1e-12)
        self.assertIsNone(row["currency_code"])

    def test_single_and_batch_identical(self):
        single = self.pipeline.predict(self.input).response_json.iloc[0]
        batch = self.pipeline.predict(pd.concat([self.input, self.input], ignore_index=True))
        self.assertEqual(batch.response_json.tolist(), [single, single])

    def test_concurrent_calls_identical(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.pipeline.predict(self.input).response_json.iloc[0], range(8)))
        self.assertEqual(len(set(results)), 1)

    def test_current_context_age(self):
        p = copy.deepcopy(self.payload)
        p["mode"] = "CURRENT_INVENTORY_MODE"
        p["context"][0]["DecisionTime"] = "2025-01-01"
        with self.assertRaisesRegex(ValueError, "CURRENT_CONTEXT_STALE_OR_FUTURE"):
            self.pipeline.score(p)

    def test_real_optimizer_baseline(self):
        columns = list(dict.fromkeys([*self.pipeline.scorer.feature_names, "PricingDecisionID", "DecisionTime", "ProductID", "StoreID", "CostPrice"]))
        f = pd.read_parquet(ROOT / "artifacts/phase8/test_factual_backtest.parquet", columns=columns).head(12)
        result = self.pipeline.score(phase3.request(f))
        baseline = pd.read_parquet(ROOT / "artifacts/phase6/test_recommendations.parquet").set_index("PricingDecisionID")
        for row in result["model_recommendations"]:
            expected = baseline.loc[row["PricingDecisionID"]]
            self.assertEqual(row["ModelOptimalCandidatePrice"], expected.ModelOptimalCandidatePrice)
            self.assertAlmostEqual(row["recommended_expected_gross_profit"], expected.recommended_expected_gross_profit, places=8)

    def test_simulation(self):
        p = copy.deepcopy(self.payload)
        row = p["context"][0]
        p["candidate_prices"] = {row["PricingDecisionID"]: row["CurrentPrice"]}
        simulations = self.pipeline.score(p)["simulations"]
        self.assertEqual(len(simulations), 1)
        self.assertTrue(simulations[0]["passes_all_pricing_rules"])

    def test_support_limit(self):
        p = copy.deepcopy(self.payload)
        row = p["context"][0]
        p["candidate_prices"] = {row["PricingDecisionID"]: row["CurrentPrice"] * 2}
        with self.assertRaisesRegex(ValueError, "MODEL_SUPPORT_LIMIT"):
            self.pipeline.score(p)

    def test_pii_outcome_and_unknown_fields_rejected(self):
        for name in ("CustomerID", "PurchasedFlag", "ActualRevenue", "unexpected"):
            p = copy.deepcopy(self.payload)
            p["context"][0][name] = "x"
            with self.assertRaises(ValueError):
                self.pipeline.score(p)

    def test_required_sources_not_inferred(self):
        for name in ("rules", "promotions", "inventory"):
            p = copy.deepcopy(self.payload)
            del p[name]
            with self.assertRaisesRegex(ValueError, "BUSINESS_SOURCE_REQUIRED"):
                self.pipeline.score(p)

    def test_missing_feature_rejected(self):
        p = copy.deepcopy(self.payload)
        del p["context"][0]["weather_temperature"]
        with self.assertRaisesRegex(ValueError, "FEATURE_CONTRACT_INCOMPLETE"):
            self.pipeline.score(p)

    def test_bad_price_and_channel(self):
        for name, value in (("CurrentPrice", 0), ("CostPrice", float("inf")), ("Channel", "whatsapp")):
            p = copy.deepcopy(self.payload)
            p["context"][0][name] = value
            with self.assertRaises(ValueError):
                self.pipeline.score(p)

    def test_future_context(self):
        p = copy.deepcopy(self.payload)
        p["context"][0]["selected_behavior_event_at"] = "2099-01-01"
        with self.assertRaisesRegex(ValueError, "FUTURE_CONTEXT_REJECTED"):
            self.pipeline.score(p)

    def test_input_signature(self):
        with self.assertRaisesRegex(ValueError, "MLFLOW_INPUT_SCHEMA_INVALID"):
            self.pipeline.predict(pd.DataFrame({"wrong": ["x"]}))
        with self.assertRaisesRegex(ValueError, "NONFINITE_JSON"):
            self.pipeline.predict(pd.DataFrame({"request_json": ["{\"x\":NaN}"]}))

    def test_no_row_data_in_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            path = phase3.inference_bundle(Path(folder) / "inference")
            self.assertFalse(list(path.rglob("*.parquet")))
            self.assertTrue((path / "artifacts/phase4/models/purchase_catboost.cbm").exists())
            with self.assertRaises(RuntimeError):
                phase3.inference_bundle(path)

    def test_plan_no_compute(self):
        p = phase3.plan()
        self.assertFalse(p["contains_row_level_data"])
        self.assertFalse(p["dedicated_endpoint"])
        self.assertLess(p["package_bytes"], 4_000_000)

    def test_business_capture_corruption_rejected_before_scoring(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as folder:
            path = Path(folder)
            (path / "rules.parquet").write_bytes(b"changed")
            (path / "manifest.json").write_text(json.dumps({"schema_version": "pricing.policy_snapshot.v1",
                "files": [{"path": "rules.parquet", "sha256": "0" * 64, "rows": 200}]}))
            with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                phase3.validate_business(path)

    def test_inventory_missing_and_out_of_stock(self):
        from inventory_policy.inventory_loader import INVENTORY_COLUMNS
        p = copy.deepcopy(self.payload)
        row = p["context"][0]
        row["DecisionTime"] = "2025-12-20"
        p["mode"] = "CURRENT_INVENTORY_MODE"
        missing = self.pipeline.score(p)["decisions"][0]
        self.assertTrue(missing["manual_review_flag"])
        self.assertIn("INVENTORY_UNAVAILABLE", missing["FinalAction"])
        inv = dict.fromkeys(INVENTORY_COLUMNS, 0)
        inv.update(InventoryID="INV-SENSITIVITY", ProductID=row["ProductID"], StoreID=row["StoreID"],
                   SnapshotDate="2025-12-31", StockStatus="Out of Stock")
        p["inventory"] = [inv]
        out = self.pipeline.score(p)["decisions"][0]
        self.assertEqual(out["FinalAction"], "OUT_OF_STOCK_NO_PRICE_ACTION")
        self.assertIsNone(out["FinalRecommendedPrice"])
        self.assertIsNone(out["expected_units"])

    def test_promotion_overlap_is_review_not_invented_discount(self):
        p = copy.deepcopy(self.payload)
        row = p["context"][0]
        p["promotions"] = [{"PromotionID": "PROMO-SENSITIVITY-" + str(i), "PromotionName": "Overlap test",
            "CategoryID": row["CategoryID"], "DiscountPct": discount, "Season": "All",
            "StartDate": "2020-01-01", "EndDate": "2030-12-31", "ActiveFlag": True}
            for i, discount in enumerate((10, 20))]
        result = self.pipeline.score(p)["decisions"][0]
        self.assertTrue(result["promotion_conflict_flag"])
        self.assertTrue(result["manual_review_flag"])
        self.assertIsNone(result["RecommendedPromotionID"])

    def test_rule_ceiling_and_simulation_rejection(self):
        from business_rules.rule_loader import PRICING_RULE_COLUMNS
        p = copy.deepcopy(self.payload)
        row = p["context"][0]
        rule = dict.fromkeys(PRICING_RULE_COLUMNS, None)
        rule.update(PricingRuleID="RULE-SENSITIVITY", RuleName="Explicit ceiling", ProductID=row["ProductID"],
            MaxPrice=row["CurrentPrice"], Priority=10, EffectiveFrom="2020-01-01", EffectiveTo="2030-12-31", ActiveFlag=True)
        p["rules"] = [rule]
        p["candidate_prices"] = {row["PricingDecisionID"]: row["CurrentPrice"] * 1.05}
        result = self.pipeline.score(p)
        self.assertLessEqual(result["decisions"][0]["FinalRecommendedPrice"], row["CurrentPrice"])
        self.assertFalse(result["simulations"][0]["passes_all_pricing_rules"])
        original = result["decisions"]
        del p["candidate_prices"]
        self.assertEqual(original, self.pipeline.score(p)["decisions"])

    def test_conflicting_price_bounds_require_review(self):
        from business_rules.rule_loader import PRICING_RULE_COLUMNS
        p = copy.deepcopy(self.payload)
        row = p["context"][0]
        rule = dict.fromkeys(PRICING_RULE_COLUMNS, None)
        rule.update(PricingRuleID="RULE-CONFLICT", RuleName="Conflict test", ProductID=row["ProductID"],
            MinPrice=row["CurrentPrice"] * 1.10, MaxPrice=row["CurrentPrice"] * .90,
            Priority=10, EffectiveFrom="2020-01-01", EffectiveTo="2030-12-31", ActiveFlag=True)
        p["rules"] = [rule]
        result = self.pipeline.score(p)["decisions"][0]
        self.assertTrue(result["manual_review_flag"])

    def test_mlflow_authentication_restores_environment(self):
        import os
        from types import SimpleNamespace
        from phase3_live import authentication
        previous = os.environ.get("DATABRICKS_TOKEN")
        client = SimpleNamespace(config=SimpleNamespace(token="test-only-placeholder"))
        with authentication(client, "https://example.invalid"):
            self.assertEqual(os.environ["DATABRICKS_TOKEN"], "test-only-placeholder")
        self.assertEqual(os.environ.get("DATABRICKS_TOKEN"), previous)

    def test_explicit_resolution_batch_and_immutable_output(self):
        from pricing_mlflow.serving import PricingService, persist_decisions
        from business_rules.rule_loader import PRICING_RULE_COLUMNS
        from promotions.promotion_loader import PROMOTION_COLUMNS
        from inventory_policy.inventory_loader import INVENTORY_COLUMNS
        context = pd.DataFrame(self.payload["context"])
        service = PricingService(self.pipeline, context, pd.DataFrame(columns=PRICING_RULE_COLUMNS),
            pd.DataFrame(columns=PROMOTION_COLUMNS), pd.DataFrame(columns=INVENTORY_COLUMNS))
        row = context.iloc[0]
        single = service.recommend(row.ProductID, row.StoreID, row.Channel, row.DecisionTime)
        batch = service.batch(context)
        self.assertEqual(single["decisions"], batch["decisions"])
        with self.assertRaisesRegex(ValueError, "SUPPORTED_CONTEXT_NOT_FOUND"):
            service.resolve("missing", row.StoreID, row.Channel, row.DecisionTime)
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_SNAPSHOT_AS_OF"):
            service.resolve(row.ProductID, row.StoreID, row.Channel, "2026-09-16")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "decisions.json"
            self.assertTrue(persist_decisions(batch, path)["created"])
            self.assertFalse(persist_decisions(batch, path)["created"])
            with self.assertRaisesRegex(ValueError, "IMMUTABLE_BATCH_OUTPUT_COLLISION"):
                persist_decisions({**batch, "mode": "different"}, path)


if __name__ == "__main__":
    unittest.main()
