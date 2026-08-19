"""Auditable recommendation table with deterministic detail views."""

from __future__ import annotations

from app.common import cached_decisions, format_num, format_price, services, setup_page, sidebar_status


AUDIT_COLUMNS = [
    "PricingDecisionID", "ProductID", "StoreID", "Channel", "CurrentPrice", "Phase6ModelOptimalCandidatePrice", "FinalRecommendedPrice", "FinalAction", "PricingRuleID", "PromotionAction", "MarkdownAction", "expected_units", "expected_revenue", "expected_gross_profit", "manual_review_flag",
]


def render() -> None:
    import streamlit as st

    setup_page("Decision Audit", "Review governed actions, reason codes, support and manual-review status")
    reg, recommendations, simulation, performance, explanation = services()
    sidebar_status(reg)
    if reg.validate_integrity()["status"] != "PASS":
        return
    split = "current" if st.toggle("Current snapshot inventory decisions", value=False) else "validation"
    frame = cached_decisions(split)
    st.markdown("### Audit filters")
    cols = st.columns(3)
    with cols[0]:
        action = st.selectbox("Action", ["All", "Price Increase", "Price Decrease", "Hold", "Promotion Review", "Markdown", "Manual Review"])
    with cols[1]:
        manual = st.selectbox("Manual review", ["All", "Manual review only", "Automatic only"])
    with cols[2]:
        limit = st.slider("Rows", min_value=10, max_value=100, value=50, step=10)
    filtered = frame.copy()
    if action != "All":
        if action == "Manual Review":
            filtered = filtered.loc[filtered["manual_review_flag"].astype(bool)]
        elif action == "Hold":
            filtered = filtered.loc[filtered["FinalAction"].astype(str).str.contains("HOLD", case=False, regex=False) | (filtered["price_change_amount"].abs() < 0.005)]
        elif action == "Price Increase":
            filtered = filtered.loc[filtered["FinalAction"].astype(str).str.contains("INCREASE", case=False, regex=False)]
        elif action == "Price Decrease":
            filtered = filtered.loc[filtered["FinalAction"].astype(str).str.contains("DECREASE|MARKDOWN", case=False, regex=True)]
        elif action == "Markdown":
            filtered = filtered.loc[filtered["MarkdownAction"].astype(str).str.contains("MARKDOWN", case=False, regex=False)]
        else:
            filtered = filtered.loc[filtered["PromotionAction"].astype(str).str.contains("REVIEW|PROMOTION", case=False, regex=True)]
    if manual == "Manual review only":
        filtered = filtered.loc[filtered["manual_review_flag"].astype(bool)]
    elif manual == "Automatic only":
        filtered = filtered.loc[~filtered["manual_review_flag"].astype(bool)]
    if filtered.empty:
        st.info("No recommendations match the selected filters.")
        return
    table = filtered[[column for column in AUDIT_COLUMNS if column in filtered.columns]].head(limit).copy()
    table = table.rename(columns={"Phase6ModelOptimalCandidatePrice": "ModelOptimalCandidatePrice", "expected_units": "ExpectedUnits", "expected_revenue": "ExpectedRevenue", "expected_gross_profit": "ExpectedGrossProfit"})
    st.dataframe(table, hide_index=True, use_container_width=True)
    selected = st.selectbox("Open audit detail", table["PricingDecisionID"].astype(str).tolist())
    rec = recommendations.get_pricing_recommendation(selected, split=split)
    with st.expander("Audit detail", expanded=True):
        rule = recommendations.get_business_rule_details(selected, split=split)
        st.json({"recommendation": rec, "business_rule": rule, "support": simulation.support_envelope(selected, split=split)})
        if split == "current":
            inventory = recommendations.get_current_inventory_insight(limit=100)
            match = [row for row in inventory if row["PricingDecisionID"] == selected]
            st.write({"Current snapshot inventory context": match[0] if match else None})
        else:
            st.caption("Historical inventory is not available for validation/test decisions; no historical inventory is inferred.")
        st.caption("Model-implied economics and rule checks are advisory. No automatic price writeback is available.")


if __name__ == "__main__":
    render()
