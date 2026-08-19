"""Browse and explain governed Phase 7 recommendations."""

from __future__ import annotations

import pandas as pd

from app.common import badge, cached_decisions, format_num, format_pct, format_price, kpi, services, setup_page, sidebar_status


REASON_LABELS = {
    "SLOW_MOVING": "Slow-moving product context applied",
    "SEASONAL": "Seasonal product context applied",
    "MARKDOWN_POLICY": "Current inventory markdown policy applied",
    "PHASE6_PRICE_CHANGED_BY_PHASE7": "Business-rule layer changed the model-optimal price",
    "RULE_MAX_PRICE_CHANGE": "Maximum allowed price movement applied",
}


def _journey(st, current: object, model: object, final: object, action: object) -> None:
    st.markdown(
        f'<div class="journey"><div class="journey-step"><b>Current Price</b><span>{format_price(current)}</span></div><div class="journey-arrow">→</div><div class="journey-step"><b>Model Optimal Price</b><span>{format_price(model)}</span></div><div class="journey-arrow">→</div><div class="journey-step"><b>Business Rules</b><span>Applied</span></div><div class="journey-arrow">→</div><div class="journey-step"><b>Promotion / Markdown / Inventory</b><span>{str(action).replace("_", " ")}</span></div><div class="journey-arrow">→</div><div class="journey-step"><b>Final Recommended Price</b><span>{format_price(final)}</span></div></div>',
        unsafe_allow_html=True,
    )


def render() -> None:
    import streamlit as st

    setup_page("Recommendation Explorer", "Inspect the current → model-optimal → governed final price journey")
    reg, recommendations, simulation, performance, explanation = services()
    sidebar_status(reg)
    if reg.validate_integrity()["status"] != "PASS":
        return
    use_current = st.toggle("Use current snapshot inventory decisions", value=False)
    split = "current" if use_current else "validation"
    decisions = cached_decisions(split)
    st.markdown("### Find a pricing decision")
    filters = st.columns(5)
    with filters[0]:
        decision_id = st.text_input("PricingDecisionID", placeholder="Search ID")
    with filters[1]:
        product = st.text_input("ProductID", placeholder="Optional")
    with filters[2]:
        store = st.text_input("StoreID", placeholder="Optional")
    with filters[3]:
        channel = st.selectbox("Channel", ["All", *sorted(decisions["Channel"].dropna().astype(str).unique())])
    with filters[4]:
        action = st.selectbox("Final Action", ["All", *sorted(decisions["FinalAction"].dropna().astype(str).unique())])
    filtered = decisions.copy()
    for col, val in [("PricingDecisionID", decision_id), ("ProductID", product), ("StoreID", store)]:
        if val:
            filtered = filtered.loc[filtered[col].astype(str).str.contains(val, case=False, regex=False)]
    if channel != "All":
        filtered = filtered.loc[filtered["Channel"].astype(str) == channel]
    if action != "All":
        filtered = filtered.loc[filtered["FinalAction"].astype(str) == action]
    if filtered.empty:
        st.info("No recommendations match the selected filters.")
        return
    options = filtered["PricingDecisionID"].astype(str).tolist()
    selected = st.selectbox("Select a recommendation", options, index=0)
    st.session_state["selected_decision_id"] = selected
    rec = recommendations.get_pricing_recommendation(selected, split=split)
    st.markdown("### Recommendation")
    hero = st.columns(4)
    for col, label, value in zip(hero, ["CURRENT PRICE", "FINAL RECOMMENDED PRICE", "PRICE CHANGE", "ACTION"], [format_price(rec["CurrentPrice"]), format_price(rec["FinalRecommendedPrice"]), format_pct((float(rec["FinalRecommendedPrice"]) - float(rec["CurrentPrice"])) / float(rec["CurrentPrice"])) if rec["CurrentPrice"] else "—", str(rec["FinalAction"]).replace("_", " ")]):
        with col:
            kpi(label, value)
    _journey(st, rec["CurrentPrice"], rec["ModelOptimalCandidatePrice"], rec["FinalRecommendedPrice"], rec["FinalAction"])
    values = st.columns(5)
    quantity = float(reg.phase6_spec.get("phase5_mean_value", 1.0) or 1.0)
    purchase_probability = float(rec["ExpectedUnits"] or 0.0) / quantity
    for col, label, value, help_text in zip(values, ["Purchase Probability", "Expected Units", "Expected Revenue", "Expected Gross Profit", "Expected Gross Margin"], [format_pct(purchase_probability), format_num(rec["ExpectedUnits"]), format_num(rec["ExpectedRevenue"]), format_num(rec["ExpectedGrossProfit"]), format_pct(float(rec["ExpectedGrossProfit"] or 0.0) / float(rec["ExpectedRevenue"]) if rec["ExpectedRevenue"] else None)], ["Predicted purchase probability implied by the frozen expected-units stack", "Expected demand, not a guaranteed unit outcome", "Model-implied economics", "Model-implied expected gross-profit opportunity", "Expected gross profit divided by expected revenue"]):
        with col:
            kpi(label, value, help_text)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Business rule")
        rule = recommendations.get_business_rule_details(selected, split=split)
        st.table(pd.DataFrame([rule]))
    with col2:
        st.markdown("#### Promotions, markdowns and reason codes")
        st.write(f"Promotion: **{str(rec['PromotionAction']).replace('_', ' ')}**")
        st.write(f"Markdown: **{str(rec['MarkdownAction']).replace('_', ' ')}**")
        for code in rec["reason_codes"]:
            st.write(f"{badge(code)} {REASON_LABELS.get(code, 'Governed decision context')}  ")
        if rec["warnings"]:
            st.warning("; ".join(rec["warnings"]))
    st.markdown("#### Decision detail")
    detail = recommendations.explain_pricing_recommendation(selected, split=split)
    st.info(detail["explanation_text"])
    st.caption("Model-implied alternative-price economics are scenario estimates. Historical outcome fields are intentionally unavailable in this explorer.")


if __name__ == "__main__":
    render()
