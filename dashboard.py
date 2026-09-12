"""Streamlit dashboard: browse past runs without the CLI.

Reads directly from the same SQLite DB and memory/repository.py functions the
CLI uses — no new backend/API layer (see CLAUDE.md's stack choice: Streamlit,
pure Python, reads from a database). $0 to run: read-only DB access, no
LLM/network calls of its own.

    streamlit run dashboard.py
"""

from __future__ import annotations

import streamlit as st

from agent.config import get_settings
from memory.db import make_engine, make_session_factory
from memory.repository import list_runs, load_run
from verify.reconcile import reconcile_facts

st.set_page_config(page_title="Research Agent Dashboard", layout="wide")
st.title("Research / Competitor-Analysis Agent")
st.caption(
    "Every claim below traces to a cited source; disagreeing sources are "
    "flagged as conflicts, not silently picked between (see CLAUDE.md)."
)

settings = get_settings()
engine = make_engine(settings.database_url)
session_factory = make_session_factory(engine)

with session_factory() as session:
    summaries = list_runs(session)

if not summaries:
    st.info('No runs stored yet — try `research-agent run --company "<name>"`.')
    st.stop()

st.subheader("All runs")
st.dataframe(
    [
        {
            "ID": s.id,
            "Topic": s.topic,
            "Created": s.created_at.strftime("%Y-%m-%d %H:%M"),
            "Sources": s.source_count,
            "Facts": s.fact_count,
            "Brief": "yes" if s.has_brief else "no",
            "Report": "yes" if s.has_report else "no",
        }
        for s in summaries
    ],
    hide_index=True,
)

st.subheader("Run detail")
topic_by_id = {s.id: s.topic for s in summaries}
run_ids = sorted(topic_by_id, reverse=True)  # most recent first
selected_id = st.selectbox(
    "Select a run",
    run_ids,
    format_func=lambda run_id: f"#{run_id} — {topic_by_id[run_id]}",
)

with session_factory() as session:
    record = load_run(session, selected_id)

if record is None:
    st.error(f"No run with id {selected_id}.")
    st.stop()

st.markdown(f"### Run #{record.id}: {record.topic}")
st.caption(f"Created {record.created_at:%Y-%m-%d %H:%M}")

st.markdown("**Brief**")
st.write(record.brief or "_(no brief stored for this run)_")

if record.report_path:
    st.markdown(f"**Deep research PDF**: `{record.report_path}`")

st.markdown(f"**Sources ({len(record.sources)})**")
if record.sources:
    st.dataframe(
        [{"URL": s.url, "Title": s.title} for s in record.sources],
        hide_index=True,
    )
else:
    st.caption("_(none fetched for this run)_")

st.markdown(f"**Facts ({len(record.facts)})**")
if record.facts:
    st.dataframe(
        [
            {
                "Attribute": f.attribute,
                "Value": f.value,
                "Confidence": f.confidence,
                "Source": f.source_url,
            }
            for f in record.facts
        ],
        hide_index=True,
    )
else:
    st.caption("_(none extracted for this run)_")

# Recomputed on the fly, not persisted — reconcile_facts is pure and
# idempotent, same reasoning as `research-agent show` (see PROGRESS.md).
_, conflicts = reconcile_facts(record.facts)
if conflicts:
    st.markdown(f"**⚠️ {len(conflicts)} conflicting fact(s) found**")
    for conflict in conflicts:
        values = "; ".join(f"{v.value} ({v.source_url})" for v in conflict.values)
        st.warning(f"**{conflict.attribute}**: {values}")
