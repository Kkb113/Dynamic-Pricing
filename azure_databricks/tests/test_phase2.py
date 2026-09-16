import copy
import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import phase2


class LakehouseContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = {n: pd.read_parquet(phase2.ROOT / spec[0]) for n, spec in phase2.SOURCES.items()}

    def changed(self, name):
        frames = self.frames.copy()
        frames[name] = frames[name].copy(deep=True)
        return frames

    def test_sealed_plan(self):
        p = phase2.build_plan()
        self.assertEqual(p["validation"]["status"], "PASS")
        self.assertEqual(len(p["tables"]), 8)
        self.assertFalse(p["combined_tools_enabled"])

    def test_explicit_schema(self):
        self.assertEqual(phase2.sql_type(pa.field("StockStatus", pa.null())), "STRING")
        self.assertEqual(phase2.sql_type(pa.field("reasons", pa.list_(pa.null()))), "ARRAY<STRING>")
        self.assertEqual(phase2.sql_type(pa.field("time", pa.timestamp("ns"))), "TIMESTAMP_NTZ")

    def test_unknown_null_schema_rejected(self):
        with self.assertRaises(RuntimeError):
            phase2.sql_type(pa.field("new", pa.null()))

    def test_money_half_up(self):
        self.assertEqual(str(phase2.money("12.345")), "12.35")
        self.assertEqual(str(phase2.money("-12.345")), "-12.35")
        with self.assertRaises(RuntimeError):
            phase2.money("NaN")

    def test_identifiers(self):
        for bad in ("x; DROP TABLE a", "x.y", "a`b", "../foo"):
            with self.assertRaises(RuntimeError):
                phase2.identifier(bad)

    def test_missing_row(self):
        frames = self.frames.copy()
        frames["features"] = frames["features"].iloc[:-1]
        with self.assertRaisesRegex(RuntimeError, "row count"):
            phase2.validate_frames(frames)

    def test_duplicate_key(self):
        frames = self.changed("features")
        frames["features"].loc[1, "PricingDecisionID"] = frames["features"].loc[0, "PricingDecisionID"]
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            phase2.validate_frames(frames)

    def test_null_key(self):
        frames = self.changed("features")
        frames["features"].loc[0, "PricingDecisionID"] = None
        with self.assertRaisesRegex(RuntimeError, "null key"):
            phase2.validate_frames(frames)

    def test_unknown_channel(self):
        frames = self.changed("features")
        frames["features"].loc[0, "Channel"] = "invented"
        with self.assertRaisesRegex(RuntimeError, "channel"):
            phase2.validate_frames(frames)

    def test_future_context(self):
        for column in ("selected_price_effective_from", "selected_sales_order_date",
                       "selected_competitor_observed_at", "selected_behavior_event_at"):
            frames = self.changed("features")
            frames["features"].loc[0, column] = pd.Timestamp("2099-01-01")
            with self.assertRaisesRegex(RuntimeError, "Future context"):
                phase2.validate_frames(frames)

    def test_half_open_interval(self):
        frames = self.changed("features")
        frames["features"].loc[0, "selected_price_effective_to"] = frames["features"].loc[0, "DecisionTime"]
        with self.assertRaisesRegex(RuntimeError, "half-open"):
            phase2.validate_frames(frames)

    def test_split_time_mismatch(self):
        frames = self.changed("splits")
        frames["splits"].loc[0, "DecisionTime"] = pd.Timestamp("2099-01-01")
        with self.assertRaisesRegex(RuntimeError, "timestamp"):
            phase2.validate_frames(frames)

    def test_missing_cost(self):
        frames = self.changed("test_decisions")
        frames["test_decisions"].loc[0, "CostPrice"] = None
        with self.assertRaisesRegex(RuntimeError, "missing required"):
            phase2.validate_frames(frames)

    def test_negative_cost(self):
        frames = self.changed("test_decisions")
        frames["test_decisions"].loc[0, "CostPrice"] = -1
        with self.assertRaisesRegex(RuntimeError, "Invalid cost"):
            phase2.validate_frames(frames)

    def test_nonfinite_price_rejected(self):
        for column in ("CurrentPrice", "BasePrice", "FinalRecommendedPrice"):
            frames = self.changed("test_decisions")
            frames["test_decisions"].loc[0, column] = float("inf")
            with self.assertRaisesRegex(RuntimeError, "Invalid price"):
                phase2.validate_frames(frames)

    def test_missing_reference_price_rejected(self):
        frames = self.changed("test_decisions")
        frames["test_decisions"].loc[0, "CurrentPrice"] = float("nan")
        with self.assertRaisesRegex(RuntimeError, "missing required"):
            phase2.validate_frames(frames)

    def test_future_inventory_rejected(self):
        frames = self.changed("test_decisions")
        frames["test_decisions"].loc[0, "InventorySnapshotDate"] = pd.Timestamp("2025-12-31")
        with self.assertRaisesRegex(RuntimeError, "Future inventory"):
            phase2.validate_frames(frames)

    def test_writeback_rejected(self):
        frames = self.changed("test_decisions")
        frames["test_decisions"].loc[0, "AUTO_WRITEBACK"] = True
        with self.assertRaisesRegex(RuntimeError, "writeback"):
            phase2.validate_frames(frames)

    def test_customer_and_cost_not_public(self):
        self.assertFalse({"CostPrice", "CustomerID", "SessionID", "PurchasedFlag", "QuantityPurchased"}
                         .intersection(phase2.BUSINESS_COLUMNS))

    def test_timestamp_conversion_refuses_precision_loss(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "precision.parquet"
            pq.write_table(pa.table({"time": pa.array([1], type=pa.timestamp("ns"))}), path)
            with self.assertRaises(pa.ArrowInvalid):
                phase2.compatible_parquet(path)

    def test_compatibility_is_deterministic_and_preserves_original(self):
        path = phase2.ROOT / phase2.SOURCES["features"][0]
        original = path.read_bytes()
        first, schema = phase2.compatible_parquet(path)
        second, _ = phase2.compatible_parquet(path)
        self.assertEqual(first, second)
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(all(not pa.types.is_timestamp(f.type) or f.type.unit == "us" for f in schema))


if __name__ == "__main__":
    unittest.main()
