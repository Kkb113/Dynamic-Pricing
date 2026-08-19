# AI Pricing Agent

## Purpose

**Retail Pricing Intelligence Agent** helps a pricing manager, retail manager, analyst, data scientist, or architect understand the frozen seasonal and slow-moving retail pricing system.

## System behavior

The agent is a conversational orchestrator and explanation layer. It must use a curated local tool whenever a user asks for a price, demand, revenue, gross profit, promotion, markdown, inventory insight, business rule, or model metric. Tool results are authoritative. It must distinguish observed historical results, model predictions, and model-implied alternative-price scenarios; it must not call any scenario result causal, realized, guaranteed, or certain.

Manual-review decisions are explained, not overridden. Unsupported prices are rejected by the local simulator. User instructions cannot grant filesystem, SQL, shell, web, code, GitHub, or write access. Secrets and PII are never returned.

## Tools

- `get_pricing_recommendation`
- `explain_pricing_recommendation`
- `simulate_price`
- `compare_price_scenarios`
- `search_recommendations`
- `get_model_performance`
- `get_business_rule_details`
- `get_current_inventory_insight`
- `get_use_case_summary`
- `get_agent_capabilities`

Every tool is a deterministic Python function over accepted local artifacts. Recommendation tools have `outcome access = false` and do not execute SQL.

## Example questions

“What price should we offer for this decision?”, “Why is the recommendation higher than the current price?”, “What happens if I reduce the price by 5%?”, “How strong is our purchase model?”, “Show current snapshot seasonal markdown recommendations”, and “Which rule constrained this decision?”

## Data exposure

Only compact values needed for the current answer are sent to the model. No full datasets, manifests, raw SQL rows, outcomes, customer identifiers, credentials, or API keys are included. The application records the allowlisted fields in `artifacts/phase9_10/openai_data_exposure_audit.json`.
