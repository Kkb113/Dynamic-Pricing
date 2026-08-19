"""Presentation-ready executive dashboard."""

from __future__ import annotations

import pandas as pd

from app.common import cached_decisions, kpi, safe_plotly, services, setup_page, sidebar_status, format_num, format_pct


def render() -> None:
    import streamlit as st

    setup_page("Executive Dashboard", "Retail Pricing Intelligence Platform · Business performance at a glance")
    reg, recommendations, simulation, performance, explanation = services()
    sidebar_status(reg)
    report = reg.validate_integrity()
    if report["status"] != "PASS":
        return
    metrics = performance.get_model_performance()
    decisions = cached_decisions("validation")
    inventory = cached_decisions("current")

    cards = st.columns(5)
    with cards[0]:
        kpi("Purchase ROC-AUC", format_num(metrics["ROC-AUC"], 3), "Ranking discrimination, not individual-decision accuracy")
    with cards[1]:
        kpi("Top-Decile Lift", f'{format_num(metrics["Top-Decile Lift"], 2)}×', "Highest-scored situations compared with overall purchase rate")
    with cards[2]:
        kpi("Aggregate Demand Error", format_pct(metrics["Demand aggregate error %"], absolute=True), "Absolute signed error shown; signed value is in the detail page")
    with cards[3]:
        kpi("Aggregate Revenue Error", format_pct(metrics["Revenue aggregate error %"], absolute=True), "Historical aggregate backtest")
    with cards[4]:
        kpi("Aggregate Gross-Profit Error", format_pct(metrics["GP aggregate error %"], absolute=True), "Historical aggregate backtest")

    st.markdown("### Business evidence")
    col1, col2 = st.columns(2)
    px, go = safe_plotly()
    actions = decisions["FinalAction"].fillna("UNKNOWN").astype(str).value_counts().rename_axis("Action").reset_index(name="Decisions")
    movement = pd.Series("HOLD", index=decisions.index)
    movement.loc[pd.to_numeric(decisions["price_change_amount"], errors="coerce") > 0] = "PRICE INCREASE"
    movement.loc[pd.to_numeric(decisions["price_change_amount"], errors="coerce") < 0] = "PRICE DECREASE"
    movement_counts = movement.value_counts().rename_axis("Movement").reset_index(name="Decisions")
    with col1:
        st.markdown("**Recommendation action distribution**")
        if px:
            st.plotly_chart(px.bar(actions, x="Action", y="Decisions", color="Action", template="plotly_white"), use_container_width=True)
        else:
            st.dataframe(actions, hide_index=True, use_container_width=True)
        st.markdown("**Price increase / decrease / hold**")
        if px:
            st.plotly_chart(px.pie(movement_counts, names="Movement", values="Decisions", hole=.45, template="plotly_white"), use_container_width=True)
        else:
            st.dataframe(movement_counts, hide_index=True, use_container_width=True)
    with col2:
        st.markdown("**Observed vs predicted economics**")
        economics = pd.DataFrame([
            {"Measure": "Demand", "Observed": metrics["Actual aggregate units"], "Predicted": metrics["Predicted aggregate units"]},
            {"Measure": "Revenue", "Observed": metrics["Actual aggregate revenue"], "Predicted": metrics["Predicted aggregate revenue"]},
            {"Measure": "Gross Profit", "Observed": metrics["Actual aggregate gross profit"], "Predicted": metrics["Predicted aggregate gross profit"]},
        ]).melt(id_vars="Measure", var_name="Series", value_name="Value")
        if px:
            st.plotly_chart(px.bar(economics, x="Measure", y="Value", color="Series", barmode="group", template="plotly_white"), use_container_width=True)
        else:
            st.dataframe(economics, hide_index=True, use_container_width=True)
        st.markdown("**Current-snapshot inventory actions**")
        inventory_actions = inventory["FinalAction"].fillna("UNKNOWN").astype(str).value_counts().rename_axis("Action").reset_index(name="Decisions")
        if px:
            st.plotly_chart(px.bar(inventory_actions, x="Action", y="Decisions", color="Action", template="plotly_white"), use_container_width=True)
        else:
            st.dataframe(inventory_actions, hide_index=True, use_container_width=True)

    st.markdown("### Deterministic business interpretation")
    st.info(" ".join(metrics["business_interpretation"]))
    st.caption(metrics["caveat"])
    st.caption("Alternative-price economics are model-implied scenario estimates, not observed, causal, or guaranteed uplift.")


if __name__ == "__main__":
    render()
