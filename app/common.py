"""Shared Streamlit presentation helpers and cached service wiring."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from app_services.artifact_registry import ArtifactRegistry
from app_services.explanation_service import ExplanationService
from app_services.model_performance_service import ModelPerformanceService
from app_services.recommendation_service import RecommendationService
from app_services.simulation_service import SimulationService

try:
    import streamlit as st
except ImportError:  # pragma: no cover - allows service/module smoke imports
    st = None


ROOT = Path(__file__).resolve().parents[1]


def registry() -> ArtifactRegistry:
    if st is not None:
        @st.cache_resource(show_spinner=False)
        def _cached() -> ArtifactRegistry:
            return ArtifactRegistry(ROOT)

        return _cached()
    return ArtifactRegistry(ROOT)


def services() -> tuple[ArtifactRegistry, RecommendationService, SimulationService, ModelPerformanceService, ExplanationService]:
    reg = registry()
    return reg, RecommendationService(reg), SimulationService(reg), ModelPerformanceService(reg), ExplanationService(RecommendationService(reg))


def cached_decisions(split: str = "validation") -> pd.DataFrame:
    if st is not None:
        @st.cache_data(show_spinner=False)
        def _cached(name: str) -> pd.DataFrame:
            return registry().load_decisions(name)

        return _cached(split)
    return registry().load_decisions(split)


def cached_surface(decision_id: str) -> pd.DataFrame:
    if st is not None:
        @st.cache_data(show_spinner=False)
        def _cached(identifier: str) -> pd.DataFrame:
            return SimulationService(registry()).candidate_surface(identifier)

        return _cached(decision_id)
    return SimulationService(registry()).candidate_surface(decision_id)


def setup_page(title: str, subtitle: str | None = None) -> None:
    if st is None:
        raise RuntimeError("Streamlit is required to run the local application; install project dependencies first")
    st.set_page_config(page_title=title, page_icon="▦", layout="wide", initial_sidebar_state="expanded")
    st.markdown(
        """
        <style>
        :root { --ink:#152238; --muted:#65758b; --line:#dfe6ee; --accent:#1769aa; --good:#16805c; --warn:#a15c00; }
        .block-container { padding-top: 2rem; max-width: 1500px; }
        .brand-title { color:var(--ink); font-size:2.05rem; font-weight:750; letter-spacing:-.03em; margin-bottom:.2rem; }
        .brand-subtitle { color:var(--muted); font-size:1rem; margin-bottom:1.4rem; }
        .kpi-card { border:1px solid var(--line); border-radius:12px; padding:1rem 1.1rem; background:#fff; min-height:116px; box-shadow:0 2px 8px rgba(21,34,56,.035); }
        .kpi-label { color:var(--muted); font-size:.82rem; text-transform:uppercase; letter-spacing:.06em; }
        .kpi-value { color:var(--ink); font-size:1.75rem; font-weight:700; margin-top:.3rem; }
        .status-pill { border:1px solid var(--line); border-radius:999px; padding:.18rem .55rem; font-size:.75rem; display:inline-block; margin:.1rem .2rem .1rem 0; }
        .status-ready { color:var(--good); background:#edf9f4; border-color:#bdebd8; }
        .status-muted { color:var(--muted); background:#f6f8fb; }
        .status-warn { color:var(--warn); background:#fff7e8; border-color:#f2d39d; }
        .journey { display:flex; align-items:stretch; gap:.45rem; margin:.5rem 0 1rem; }
        .journey-step { flex:1; border:1px solid var(--line); border-radius:10px; padding:.75rem; background:#fafcff; }
        .journey-step b { display:block; color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; }
        .journey-step span { display:block; color:var(--ink); font-size:1.1rem; font-weight:650; margin-top:.2rem; }
        .journey-arrow { color:var(--muted); align-self:center; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="brand-title">AI-Driven Dynamic Pricing &amp; Promotion Optimization</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="brand-subtitle">{subtitle or "Retail Pricing Intelligence Platform · Model-driven demand, pricing and profitability intelligence for seasonal and slow-moving products."}</div>', unsafe_allow_html=True)


def sidebar_status(reg: ArtifactRegistry | None = None) -> None:
    if st is None:
        return
    reg = reg or registry()
    report = reg.validate_integrity()
    st.sidebar.markdown("### Pricing platform")
    status = "Ready" if report["status"] == "PASS" else "Integrity failure"
    st.sidebar.markdown(f'<span class="status-pill {"status-ready" if status == "Ready" else "status-warn"}">Pricing Engine&nbsp;&nbsp;{status}</span>', unsafe_allow_html=True)
    st.sidebar.markdown('<span class="status-pill status-ready">Frozen Model&nbsp;&nbsp;Loaded</span>', unsafe_allow_html=True)
    st.sidebar.markdown('<span class="status-pill status-ready">Business Rules&nbsp;&nbsp;Loaded</span>', unsafe_allow_html=True)
    ai_ready = bool(os.getenv("OPENAI_API_KEY", "").strip() and os.getenv("OPENAI_MODEL", "").strip())
    st.sidebar.markdown(f'<span class="status-pill {"status-ready" if ai_ready else "status-muted"}">AI Agent&nbsp;&nbsp;{"Connected" if ai_ready else "Not Configured"}</span>', unsafe_allow_html=True)
    st.sidebar.divider()
    st.sidebar.caption("Advisory pricing intelligence")
    st.sidebar.caption("No automatic price writeback")
    if report["status"] != "PASS":
        st.error("ARTIFACT_INTEGRITY_FAILURE — recommendations and simulation are disabled until accepted artifacts are restored.")


def kpi(label: str, value: str, help_text: str | None = None) -> None:
    if st is None:
        return
    hint = f' title="{help_text}"' if help_text else ""
    st.markdown(f'<div class="kpi-card"{hint}><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>', unsafe_allow_html=True)


def format_price(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return "—"
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def format_pct(value: Any, digits: int = 1, absolute: bool = False) -> str:
    try:
        if value is None or pd.isna(value):
            return "—"
        val = float(value) * 100
        if absolute:
            val = abs(val)
        return f"{val:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def format_num(value: Any, digits: int = 2) -> str:
    try:
        if value is None or pd.isna(value):
            return "—"
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def badge(action: str) -> str:
    return f'<span class="status-pill status-ready">{str(action).replace("_", " ")}</span>'


def safe_plotly():
    try:
        import plotly.express as px
        import plotly.graph_objects as go

        return px, go
    except ImportError:
        return None, None


__all__ = ["ROOT", "badge", "cached_decisions", "cached_surface", "format_num", "format_pct", "format_price", "kpi", "registry", "safe_plotly", "services", "setup_page", "sidebar_status"]
