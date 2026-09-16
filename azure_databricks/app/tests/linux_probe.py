"""Load the actual App payload in a Linux container, not a rebuilt model."""
import json
import sys

from dynamic_pricing_app.runtime import PricingRuntime

if __name__ == "__main__":
    runtime = PricingRuntime.load(sys.argv[1] if len(sys.argv) > 1 else "/payload")
    result = runtime.recommend("PRO002461", "STO000037", "Store")
    assert result["suggested_price"] == 61.28, "Accepted model parity failed"
    print(json.dumps({"status": "PASS_LINUX_PAYLOAD", "suggested_price": result["suggested_price"]}))
