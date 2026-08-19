"""Conversational showcase page for the curated Pricing Intelligence Agent."""

from __future__ import annotations

import re

from app.common import format_num, format_pct, format_price, kpi, registry, services, setup_page, sidebar_status
from ai_agent.agent import run_agent


SUGGESTIONS = [
    "What does this pricing solution do?",
    "How well is the model performing?",
    "Why is this price being increased?",
    "Compare current and recommended price.",
    "What happens if I try another supported price?",
    "Show seasonal slow-moving markdown recommendations.",
    "Which business rule constrained this decision?",
]


def render() -> None:
    import streamlit as st

    setup_page("AI Pricing Agent", "Ask questions about recommendations, economics, rules, promotions and markdowns")
    reg, recommendations, simulation, performance, explanation = services()
    sidebar_status(reg)
    if reg.validate_integrity()["status"] != "PASS":
        return
    st.markdown("## Retail Pricing Intelligence Agent")
    st.caption("The agent is an orchestrator and explanation layer. Frozen local pricing tools remain authoritative.")

    st.markdown("**Suggested questions**")
    cols = st.columns(3)
    for index, prompt in enumerate(SUGGESTIONS):
        with cols[index % 3]:
            if st.button(prompt, key=f"suggestion_{index}", use_container_width=True):
                st.session_state["pending_agent_prompt"] = prompt

    selected_id = st.text_input("Optional PricingDecisionID for the structured evidence card", value=st.session_state.get("selected_decision_id", ""), placeholder="PDL000000000029917")
    if selected_id:
        st.session_state["selected_decision_id"] = selected_id
    prompt = st.chat_input("Ask the Pricing Intelligence Agent")
    prompt = prompt or st.session_state.pop("pending_agent_prompt", None)
    if "agent_history" not in st.session_state:
        st.session_state["agent_history"] = []
    for item in st.session_state["agent_history"]:
        with st.chat_message(item["role"]):
            st.markdown(item["text"])
            if item.get("tools"):
                with st.expander("Agent Tools Used", expanded=False):
                    for tool in item["tools"]:
                        st.write(f"✓ {tool}")
    if prompt:
        st.session_state["agent_history"].append({"role": "user", "text": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Consulting frozen pricing tools…"):
                result = run_agent(prompt, reg)
            st.markdown(result.text)
            if result.error:
                st.caption("The dashboard and local pricing engine remain available without conversational access.")
            with st.expander("Agent Tools Used", expanded=False):
                if result.tool_names:
                    for tool in result.tool_names:
                        st.write(f"✓ {tool}")
                else:
                    st.caption("No tool activity captured (offline or unavailable agent).")
            st.session_state["agent_history"].append({"role": "assistant", "text": result.text, "tools": result.tool_names})

    if selected_id:
        try:
            rec = recommendations.get_pricing_recommendation(selected_id)
        except KeyError:
            st.warning("No recommendation matches that PricingDecisionID.")
        else:
            st.markdown("### Authoritative structured recommendation")
            cards = st.columns(6)
            for col, label, value in zip(cards, ["Current Price", "Recommended Price", "Final Action", "Expected Units", "Expected Revenue", "Expected Gross Profit"], [format_price(rec["CurrentPrice"]), format_price(rec["FinalRecommendedPrice"]), str(rec["FinalAction"]).replace("_", " "), format_num(rec["ExpectedUnits"]), format_num(rec["ExpectedRevenue"]), format_num(rec["ExpectedGrossProfit"])]):
                with col:
                    kpi(label, value)
            st.caption("These values are returned by the frozen Phase 7 recommendation artifact; the LLM cannot replace them.")


if __name__ == "__main__":
    render()
