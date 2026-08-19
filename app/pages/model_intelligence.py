"""Model credibility and aggregate backtest evidence."""

from __future__ import annotations

import json

import pandas as pd

from app.common import format_num, format_pct, kpi, safe_plotly, services, setup_page, sidebar_status


def render() -> None:
    import streamlit as st

    setup_page("Model Intelligence", "Why the frozen purchase, demand and economic stack is credible")
    reg, recommendations, simulation, performance, explanation = services()
    sidebar_status(reg)
    if reg.validate_integrity()["status"] != "PASS":
        return
    metrics = performance.get_model_performance()
    st.markdown("### Purchase model")
    cards = st.columns(5)
    for col, label, value, help_text in zip(cards, ["CatBoost ROC-AUC", "Average Precision", "Top-Decile Lift", "Log Loss", "Brier Score"], [format_num(metrics["ROC-AUC"], 4), format_num(metrics["Average Precision"], 4), f'{format_num(metrics["Top-Decile Lift"], 2)}×', format_num(metrics["Log Loss"], 4), format_num(metrics["Brier Score"], 4)], ["Ranking discrimination, not accuracy", "Precision-recall ranking evidence", "Top-scored purchase rate relative to overall rate", "Probabilistic loss", "Probability calibration loss"]):
        with col:
            kpi(label, value, help_text)
    metric_path = reg.root / "artifacts/phase4/test_metrics.json"
    if metric_path.exists():
        comparison = json.loads(metric_path.read_text(encoding="utf-8"))
        table = pd.DataFrame({name.title(): {"ROC-AUC": values.get("roc_auc"), "Average Precision": values.get("average_precision"), "Top-Decile Lift": values.get("top_decile_lift")} for name, values in comparison.items()}).T.reset_index(names="Model")
        px, go = safe_plotly()
        if px:
            st.plotly_chart(px.bar(table.melt(id_vars="Model"), x="Model", y="value", color="variable", barmode="group", template="plotly_white"), use_container_width=True)
        else:
            st.dataframe(table, hide_index=True, use_container_width=True)
    st.markdown("### Demand and economic backtest")
    cols = st.columns(3)
    with cols[0]:
        st.markdown("**Demand**")
        st.write(f"Actual units: **{format_num(metrics['Actual aggregate units'])}**")
        st.write(f"Predicted units: **{format_num(metrics['Predicted aggregate units'])}**")
        st.write(f"Aggregate error: **{format_pct(metrics['Demand aggregate error %'], absolute=True)}**")
        st.write(f"MAE / RMSE: **{format_num(metrics['demand_mae'])} / {format_num(metrics['demand_rmse'])}**")
    with cols[1]:
        st.markdown("**Revenue**")
        st.write(f"Actual revenue: **{format_num(metrics['Actual aggregate revenue'])}**")
        st.write(f"Predicted revenue: **{format_num(metrics['Predicted aggregate revenue'])}**")
        st.write(f"Aggregate error: **{format_pct(metrics['Revenue aggregate error %'], absolute=True)}**")
        st.write(f"MAE / RMSE: **{format_num(metrics['revenue_mae'])} / {format_num(metrics['revenue_rmse'])}**")
    with cols[2]:
        st.markdown("**Gross profit**")
        st.write(f"Actual GP: **{format_num(metrics['Actual aggregate gross profit'])}**")
        st.write(f"Predicted GP: **{format_num(metrics['Predicted aggregate gross profit'])}**")
        st.write(f"Aggregate error: **{format_pct(metrics['GP aggregate error %'], absolute=True)}**")
        st.write(f"Margin observed / predicted: **{format_pct(metrics['Observed margin rate'])} / {format_pct(metrics['Predicted margin rate'])}**")
    with st.expander("Important model caveat", expanded=True):
        st.warning(metrics["caveat"])
    st.info("The highest-scored pricing situations contain substantially more purchasers than the overall population. This is ranking signal, not a claim that each individual decision is predicted correctly.")


if __name__ == "__main__":
    render()
