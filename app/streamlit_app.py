"""Local Streamlit entry point for the final pricing application."""

from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

try:
    import streamlit as st
except ImportError:  # pragma: no cover - import smoke test in minimal env
    st = None

from app.common import registry, setup_page, sidebar_status


def render_executive_dashboard() -> None:
    from app.pages.executive_dashboard import render

    render()


def main() -> None:
    if st is None:
        raise RuntimeError("Install the project dependencies to run Streamlit")
    render_executive_dashboard()


if __name__ == "__main__":
    main()
