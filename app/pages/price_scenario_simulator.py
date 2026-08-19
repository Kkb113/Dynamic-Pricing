"""Interactive frozen Phase 6/7 scenario simulator."""

from __future__ import annotations

import pandas as pd

from app.common import cached_decisions, format_num, format_pct, format_price, kpi, safe_plotly, services, setup_page, sidebar_status
from app_services.simulation_service import SimulationError


METRIC_OPTIONS = {
    "Purchase Probability": "raw_purchase_probability",
    "Expected Units": "safe_expected_units",
    "Expected Revenue": "expected_revenue",
    "Expected Gross Profit": "expected_gross_profit",
}


def render() -> None:
    import streamlit as st

    setup_page("Price Scenario Simulator", "Compare supported candidate prices and model-implied expected economics")
    reg, recommendations, simulation, performance, explanation = services()
    sidebar_status(reg)
    if reg.validate_integrity()["status"] != "PASS":
        return
    decisions = cached_decisions("validation")
    selected = st.selectbox("PricingDecisionID", decisions["PricingDecisionID"].astype(str).tolist(), index=0)
    rec = recommendations.get_pricing_recommendation(selected)
    surface = simulation.candidate_surface(selected)
    envelope = simulation.support_envelope(selected)
    st.caption(f"Frozen model support: {format_price(envelope['support_low_price'])} to {format_price(envelope['support_high_price'])}. Unsupported prices are rejected without extrapolation.")
    chart_metric = st.selectbox("Chart measure", list(METRIC_OPTIONS))
    col = METRIC_OPTIONS[chart_metric]
    px, go = safe_plotly()
    if px:
        figure = px.line(surface, x="CandidatePrice", y=col, markers=True, template="plotly_white", labels={"CandidatePrice": "Candidate Price", col: chart_metric})
        markers = [("Current Price", rec["CurrentPrice"]), ("Phase 6 Model-Optimal Price", rec["ModelOptimalCandidatePrice"]), ("Phase 7 Final Recommended Price", rec["FinalRecommendedPrice"])]
        for label, price in markers:
            if price is not None:
                figure.add_vline(x=float(price), line_dash="dot", annotation_text=label, annotation_position="top")
        st.plotly_chart(figure, use_container_width=True)
    else:
        st.dataframe(surface[["CandidatePrice", col]], hide_index=True, use_container_width=True)
    display_cols = ["CandidatePrice", "raw_purchase_probability", "safe_expected_units", "expected_revenue", "expected_gross_profit", "candidate_margin_pct"]
    table = surface[display_cols].rename(columns={"raw_purchase_probability": "Purchase Probability", "safe_expected_units": "Expected Units", "expected_revenue": "Expected Revenue", "expected_gross_profit": "Expected Gross Profit", "candidate_margin_pct": "Margin %"}).copy()
    rule = recommendations.get_business_rule_details(selected)
    table["Business Rule Compliance"] = table["CandidatePrice"].between(float(rule["effective_price_floor"]), float(rule["effective_price_ceiling"])) & (table["CandidatePrice"] >= float(surface["CostPrice"].iloc[0]))
    st.markdown("### Scenario table")
    st.dataframe(table, hide_index=True, use_container_width=True)

    st.markdown("### Try another price")
    custom = st.number_input("Candidate price", min_value=0.01, value=float(rec["FinalRecommendedPrice"] or rec["CurrentPrice"]), step=0.01, format="%.2f")
    if st.button("Simulate Price", type="primary"):
        with st.spinner("Scoring supported price through the frozen engine…"):
            try:
                result = simulation.simulate_price(selected, custom)
            except SimulationError as exc:
                if exc.code == "MODEL_SUPPORT_LIMIT":
                    st.error("This price lies outside the range supported by the historical training data and will not be scored automatically.")
                else:
                    st.error(str(exc))
            else:
                cards = st.columns(5)
                for c, label, value in zip(cards, ["Purchase Probability", "Expected Units", "Expected Revenue", "Expected Gross Profit", "Rule Compliance"], [format_pct(result["purchase_probability"]), format_num(result["expected_units"]), format_num(result["expected_revenue"]), format_num(result["expected_gross_profit"]), "Compliant" if result["business_rule_compliance"] else "Review"]):
                    with c:
                        kpi(label, value)
                st.caption("Model-implied = true. This scenario is not an observed or causal result.")
                if result["rule_violations"]:
                    st.warning("; ".join(result["rule_violations"]))
                st.session_state["last_simulation"] = result
    if st.button("Ask Agent to Explain This Scenario"):
        st.session_state["pending_agent_prompt"] = f"Explain the model-implied scenario for {selected} at price {custom:.2f}. Use the simulate_price tool and do not invent a price."
        st.info("Prepared question saved for the AI Pricing Agent page.")


if __name__ == "__main__":
    render()
