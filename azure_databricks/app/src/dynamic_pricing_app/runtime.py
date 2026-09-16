"""Bounded adapter around accepted MLflow version 1; no customer-level pricing."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path

import pandas as pd

CHANNELS = {"Email", "Kiosk", "Mobile", "Online", "Store", "Web"}
SOURCE_NOTE = ("Historical synthetic scenarios; monetary values use unverified source units. "
               "Prices require business review. Expected profit is modeled, not measured revenue.")


class PricingUnavailable(RuntimeError):
    pass


def money(value):
    return None if value is None or pd.isna(value) else round(float(value), 2)


class PricingRuntime:
    def __init__(self, model, contexts, rules, promotions, inventory, *, release, products=None):
        self.model = model
        self.contexts = contexts.copy()
        self.contexts["DecisionTime"] = pd.to_datetime(self.contexts.DecisionTime)
        self.rules, self.promotions, self.inventory = rules, promotions, inventory
        self.release = release
        self.products = products or {}
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.contexts = self.contexts.sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort")

    @classmethod
    def load(cls, root):
        import mlflow
        root = Path(root).resolve()
        manifest = json.loads((root / "pricing-manifest.json").read_text())
        if manifest["model_version"] != "1" or not manifest["advisory_only"]:
            raise PricingUnavailable("PRICING_RELEASE_NOT_ACCEPTED")
        for name, expected in manifest["files"].items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise PricingUnavailable("PRICING_RELEASE_HASH_MISMATCH")
        model = mlflow.pyfunc.load_model(str(root / "model"))
        return cls(model, pd.read_parquet(root / "contexts.parquet"),
            pd.read_parquet(root / "rules.parquet"), pd.read_parquet(root / "promotions.parquet"),
            pd.read_parquet(root / "inventory.parquet"), release=manifest["release_seal"],
            products=manifest.get("product_names", {}))

    def lookup(self, product_ids=(), store_id=None, channel=None, query="", limit=5):
        data = self.contexts
        if product_ids:
            data = data[data.ProductID.isin(product_ids)]
        if store_id:
            data = data[data.StoreID.eq(store_id)]
        if channel:
            data = data[data.Channel.eq(channel)]
        if query:
            terms = query.casefold().split()
            ids = [p for p, name in self.products.items() if all(t in name.casefold() for t in terms)]
            data = data[data.ProductID.isin(ids)]
        rows = data.drop_duplicates(["ProductID", "StoreID", "Channel"], keep="last").tail(min(limit, 10))
        return [{"product_id": r.ProductID, "product_name": self.products.get(r.ProductID, r.ProductID),
                 "store_id": r.StoreID, "channel": r.Channel, "as_of": r.DecisionTime.isoformat(),
                 "current_price": money(r.CurrentPrice), "currency": "source units (unverified)"}
                for r in rows.itertuples()]

    def recommend(self, product_id, store_id, channel, as_of=None, candidate_price=None, *, timeout=3):
        if not re.fullmatch(r"PRO\d{6}", product_id) or not re.fullmatch(r"STO\d{6}", store_id) or channel not in CHANNELS:
            raise ValueError("INVALID_PRICING_IDENTIFIERS")
        subset = self.contexts[self.contexts.ProductID.eq(product_id) & self.contexts.StoreID.eq(store_id) & self.contexts.Channel.eq(channel)]
        if as_of:
            date = pd.Timestamp(as_of)
            if pd.isna(date) or date.tzinfo is not None or date > pd.Timestamp("2025-12-31 23:59:59.999999"):
                raise ValueError("ONLY_HISTORICAL_SNAPSHOT_AVAILABLE")
            subset = subset[subset.DecisionTime.le(date)]
        if subset.empty:
            raise ValueError("NO_SUPPORTED_PRODUCT_STORE_CHANNEL")
        context = subset.tail(1)
        source_date = context.DecisionTime.iloc[0]
        if as_of and (date.normalize() - source_date.normalize()).days > 30:
            raise ValueError("HISTORICAL_CONTEXT_TOO_OLD")
        if candidate_price is not None and (isinstance(candidate_price, bool) or not isinstance(candidate_price, (int, float)) or not 0 < candidate_price < 1_000_000):
            raise ValueError("INVALID_CANDIDATE_PRICE")
        key = (self.release, str(context.PricingDecisionID.iloc[0]), as_of, candidate_price)
        if not self.lock.acquire(timeout=timeout):
            raise PricingUnavailable("PRICING_BUSY")
        try:
            if key in self.cache:
                self.cache.move_to_end(key)
                return copy.deepcopy(self.cache[key])
            payload = {"schema_version": "pricing.scoring.v1", "context": json.loads(context.to_json(orient="records", date_format="iso")),
                "rules": json.loads(self.rules.to_json(orient="records", date_format="iso")),
                "promotions": json.loads(self.promotions.to_json(orient="records", date_format="iso")),
                "inventory": [], "mode": "HISTORICAL_POLICY_MODE"}
            if candidate_price is not None:
                payload["candidate_prices"] = {str(context.PricingDecisionID.iloc[0]): candidate_price}
            started = time.monotonic()
            result = json.loads(self.model.predict(pd.DataFrame({"request_json": [json.dumps(payload, allow_nan=False)]})).response_json.iloc[0])
            row = result["decisions"][0]
            manual = bool(row["manual_review_flag"])
            answer = {"product_id": product_id, "product_name": self.products.get(product_id, product_id),
                "store_id": store_id, "channel": channel, "as_of": source_date.isoformat(),
                "requested_as_of": as_of, "current_price": money(row["CurrentPrice"]),
                "suggested_price": None if manual else money(row["FinalRecommendedPrice"]),
                "review_required": True, "manual_review": manual,
                "action": str(row["FinalAction"]), "source_note": SOURCE_NOTE,
                "currency_code": None, "release": self.release, "model_version": "1",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "price_floor": money(row.get("effective_price_floor")),
                "price_ceiling": money(row.get("effective_price_ceiling")),
                "expected_gross_profit": money(row.get("expected_gross_profit")),
                "reason": "Business review is needed before proposing a price." if manual else
                    "Balances modeled demand and margin within the available business rules. The model often favors the upper price limit."}
            if result["simulations"]:
                sim = result["simulations"][0]
                answer["simulation"] = {"candidate_price": money(sim["CandidatePrice"]),
                    "expected_gross_profit": money(sim.get("expected_gross_profit")),
                    "eligible_under_current_policies": bool(sim["all_business_policies_approved"]),
                    "review_required": True, "inventory_adjusted": False}
            self.cache[key] = copy.deepcopy(answer)
            while len(self.cache) > 128:
                self.cache.popitem(last=False)
            return answer
        finally:
            self.lock.release()
