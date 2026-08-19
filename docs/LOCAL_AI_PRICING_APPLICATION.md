# Local AI Pricing Application

## Purpose

This final phase turns the accepted Phase 1–8 dynamic-pricing evidence into a local business demonstration. It is advisory-only: there is no price writeback, operational database, authentication, or cloud deployment.

## Architecture

The Streamlit UI calls a reusable `ArtifactRegistry` and service layer. Services load the frozen Phase 4 purchase model, Phase 5 quantity estimator, Phase 6 candidate economics, Phase 7 governed decisions/current snapshot inventory, and Phase 8 metrics. The OpenAI Agents SDK is an optional conversational orchestrator over ten curated function tools. It cannot access shell, SQL, files, web search, code execution, secrets, outcomes, or PII.

The authoritative path is:

`purchase probability × expected quantity if purchase = expected units → candidate economics → Phase 7 rules/promotions/markdown/inventory → final recommendation`.

The model and upstream hashes are checked at startup. A failed check displays `ARTIFACT_INTEGRITY_FAILURE` and disables recommendation/simulation actions. Candidate prices outside the frozen support envelope are rejected; they are never extrapolated.

## Screens

1. **Executive Dashboard** — Phase 8 KPIs, action distributions, observed-versus-predicted aggregate economics, current-snapshot inventory actions, and deterministic business interpretation.
2. **AI Pricing Agent** — optional natural-language explanation with visible high-level tool activity and an authoritative structured card.
3. **Recommendation Explorer** — searchable decision filters, current/model/final price journey, expected economics, rule panel, reason codes, and warnings.
4. **Price Scenario Simulator** — frozen candidate curve, scenario markers, parity table, and supported custom-price simulation.
5. **Model Intelligence** — purchase, demand, revenue, gross-profit evidence and the aggregate-calibration caveat.
6. **Decision Audit** — governed decision table and detail evidence.

## Local run

```powershell
python -m pip install -e ".[test]"
Copy-Item .env.example .env
# set OPENAI_API_KEY and OPENAI_MODEL when conversational access is desired
streamlit run app/streamlit_app.py
```

Without either OpenAI setting, all deterministic dashboard and pricing-tool features remain available. If an OpenAI call fails, the page reports that the explanation service is unavailable and leaves the pricing engine usable.

## Data governance and limitations

Recommendation tools use only compact, allowlisted fields. They do not read `PurchasedFlag`, `QuantityPurchased`, `ActualRevenue`, `OutcomeTime`, `OrderLineID`, or PII. Phase 8 metrics are already-aggregated evidence. Current inventory is labelled as a **current snapshot inventory context**, never historical inventory. Alternative prices are model-implied scenario estimates and do not establish causal or guaranteed uplift. SHAP is not presented unless a mathematically validated integration is available; this implementation records the deterministic explanation fallback.
