"""Minimal Streamlit UI for the competitor-intelligence crew.

Run with:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from competitor_intel.config import load_config
from competitor_intel.report import to_markdown
from competitor_intel.runner import run as run_flow

st.set_page_config(page_title="Competitor Intelligence Crew", page_icon="🔎")

st.title("🔎 Competitor Intelligence Crew")
st.caption(
    "Paste a few competitor URLs and get a structured comparison of pricing, "
    "features, and positioning - produced by a CrewAI multi-agent flow."
)

with st.sidebar:
    st.header("Configuration")
    config = load_config()
    provider = st.selectbox(
        "Provider", ["anthropic", "openai"], index=0 if config.provider != "openai" else 1
    )
    model = st.text_input("Model", value=config.model)
    use_cache = st.checkbox("Use scrape cache", value=config.cache_enabled)
    st.markdown(
        "Set your API key via environment variables (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`)."
    )

urls_raw = st.text_area(
    "Competitor URLs (one per line)",
    placeholder="https://competitor-a.com/pricing\nhttps://competitor-b.com/pricing",
    height=140,
)

if st.button("Run analysis", type="primary"):
    urls = [line.strip() for line in urls_raw.splitlines() if line.strip()]
    if not urls:
        st.warning("Enter at least one URL.")
        st.stop()

    config.provider = provider
    config.model = model
    config.cache_enabled = use_cache

    with st.spinner(f"Running the crew over {len(urls)} URL(s)..."):
        report = run_flow(urls, config)

    if report.cost:
        col1, col2, col3 = st.columns(3)
        col1.metric("Tokens", f"{report.cost.total_usage.total_tokens:,}")
        col2.metric("Est. cost", f"${report.cost.total_cost_usd:.4f}")
        col3.metric(
            "Usable pages",
            f"{sum(p.usable() for p in report.pages)}/{len(report.pages)}",
        )

    st.markdown(to_markdown(report))

    with st.expander("Orchestrator decision log"):
        for decision in report.decisions:
            st.write("•", decision)

    st.download_button(
        "Download JSON report",
        data=report.model_dump_json(indent=2),
        file_name="competitor-intel-report.json",
        mime="application/json",
    )
