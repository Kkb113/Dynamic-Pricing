# Final Business Solution Summary

## Business problem

Retail teams need a defensible way to price seasonal and slow-moving products while balancing purchase propensity, expected quantity, revenue, gross profit, promotions, markdown policy, inventory context, and business constraints.

## Chosen use case

**AI-Driven Dynamic Pricing & Promotion Optimization for Seasonal and Slow-Moving Retail Products.** The solution provides advisory, business-governed recommendations rather than automatic writeback.

## Data signals and ML architecture

The frozen stack uses point-in-time price, product, channel, season, store, region, demand-behavior, competitor-context, promotion, and inventory signals. A Phase 4 CatBoost purchase model supplies purchase probability; the frozen Phase 5 estimator supplies expected quantity if purchase; Phase 6 scores candidate economics; Phase 7 applies rules, promotions, markdowns, and current inventory policy; Phase 8 validates factual aggregate calibration and model-implied scenarios.

## Model performance

Phase 8 evidence is loaded dynamically in the application. The purchase model provides ranking signal and the integrated demand/economic stack is evaluated using aggregate observed-versus-predicted metrics. Aggregate calibration is stronger than individual decision-level prediction accuracy, so the UI uses expected values rather than deterministic transaction claims.

## Dynamic price simulation and governance

Users can inspect candidate curves and simulate a supported price. The application rejects prices outside the frozen support envelope, preserves response safety, shows rule compliance, and labels alternative economics as model-implied scenario estimates. Current inventory is explicitly a current snapshot context.

## AI Pricing Agent and dashboard

The optional OpenAI Agents SDK agent calls only curated local pricing tools. It cannot invent a price or access outcomes, PII, SQL, files, shell, web, or write tools. The six-page Streamlit application gives stakeholders executive KPIs, recommendation journeys, scenario curves, model intelligence, and decision audit detail.

## Known limitations

There is no historical cost variation, no causal price-elasticity claim, no automatic writeback, no persistent chat database, and no cloud deployment. SHAP is represented by an honest deterministic fallback unless a validated compatibility path is available. OpenAI conversational explanations require a locally configured key/model; the deterministic application does not.
