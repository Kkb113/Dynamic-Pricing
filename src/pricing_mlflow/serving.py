"""Snapshot-aware resolution and shared batch/interactive adapters.

The caller supplies authorized, precomputed point-in-time contexts. No SQL,
network access or outcome lookup is performed by this service.
"""
import hashlib
import json
from pathlib import Path
import pandas as pd
from pricing_mlflow.pipeline import VERSION, clean


class PricingService:
    def __init__(self, pipeline, contexts, rules, promotions, inventory):
        self.pipeline = pipeline
        self.contexts = contexts.copy()
        self.contexts["DecisionTime"] = pd.to_datetime(self.contexts.DecisionTime)
        self.rules, self.promotions, self.inventory = rules.copy(), promotions.copy(), inventory.copy()

    def resolve(self, product_id, store_id, channel, as_of):
        if not all(isinstance(x, str) and x.strip() for x in (product_id, store_id, channel)):
            raise ValueError("PRODUCT_STORE_CHANNEL_REQUIRED")
        when = pd.Timestamp(as_of)
        if pd.isna(when) or when.tzinfo is not None or when > pd.Timestamp("2025-12-31 23:59:59.999999"):
            raise ValueError("UNSUPPORTED_SNAPSHOT_AS_OF")
        context = self.contexts.loc[self.contexts.ProductID.eq(product_id) & self.contexts.StoreID.eq(store_id) &
            self.contexts.Channel.eq(channel) & self.contexts.DecisionTime.le(when)]
        if context.empty:
            raise ValueError("SUPPORTED_CONTEXT_NOT_FOUND")
        context = context.sort_values(["DecisionTime", "PricingDecisionID"], kind="mergesort").tail(1)
        if (when.normalize() - context.DecisionTime.iloc[0].normalize()).days > 30:
            raise ValueError("SUPPORTED_CONTEXT_TOO_OLD")
        return context

    def _score(self, context, mode, candidate_prices=None):
        inventory = self.inventory
        if mode == "HISTORICAL_POLICY_MODE":
            inventory = inventory.iloc[:0]
        else:
            pairs = pd.MultiIndex.from_frame(context[["ProductID", "StoreID"]].drop_duplicates())
            inventory = inventory.loc[pd.MultiIndex.from_frame(inventory[["ProductID", "StoreID"]]).isin(pairs)]
        payload = {"schema_version": VERSION, "context": clean(context.to_dict("records")),
            "rules": clean(self.rules.to_dict("records")), "promotions": clean(self.promotions.to_dict("records")),
            "inventory": clean(inventory.to_dict("records")), "mode": mode}
        if candidate_prices is not None:
            payload["candidate_prices"] = candidate_prices
        return self.pipeline.score(payload)

    def recommend(self, product_id, store_id, channel, as_of, *, mode="HISTORICAL_POLICY_MODE", candidate_price=None):
        context = self.resolve(product_id, store_id, channel, as_of)
        candidate = None if candidate_price is None else {context.PricingDecisionID.iloc[0]: candidate_price}
        result = self._score(context, mode, candidate)
        result["resolution"] = {"requested_as_of": pd.Timestamp(as_of).isoformat(),
            "source_context_as_of": context.DecisionTime.iloc[0].isoformat(),
            "policy_as_of": context.DecisionTime.iloc[0].isoformat(),
            "snapshot_only": True, "feature_recomputed_for_requested_date": False}
        return result

    def batch(self, contexts, *, mode="HISTORICAL_POLICY_MODE"):
        if contexts.empty or contexts.PricingDecisionID.duplicated().any():
            raise ValueError("BATCH_CONTEXT_IDENTITY_INVALID")
        decisions = []
        for offset in range(0, len(contexts), 500):
            decisions.extend(self._score(contexts.iloc[offset:offset + 500], mode)["decisions"])
        return {"schema_version": VERSION, "mode": mode, "decisions": decisions,
                "advisory_only": True, "auto_writeback": False}


def persist_decisions(result, destination):
    """Caller-authorized path; immutable/idempotent outputs, never overwrite."""
    data = (json.dumps(clean(result), sort_keys=True, allow_nan=False) + "\n").encode()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(data)
        created = True
    except FileExistsError:
        if destination.read_bytes() != data:
            raise ValueError("IMMUTABLE_BATCH_OUTPUT_COLLISION") from None
        created = False
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "created": created}
