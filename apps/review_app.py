"""Engineer review screen (Part C7).

    streamlit run apps/review_app.py          (Windows: .venv\\Scripts\\streamlit run apps\\review_app.py)

Shows each link in the review band with its context; the engineer approves, rejects
or corrects it. Every decision is appended to data/review/decisions.csv and is used by
the next `run_all` (graph edges with method=engineer, extra training labels).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ddn.config import STAGING  # noqa: E402
from ddn.review import build_queue, load_decisions, pending, save_decision  # noqa: E402

st.set_page_config(page_title="DDN-01 link review", layout="wide")


@st.cache_data
def assets() -> pd.DataFrame:
    a = pd.read_parquet(STAGING / "assets.parquet")
    return a[["functional_location", "name", "asset_type"]]


@st.cache_data
def queue() -> pd.DataFrame:
    return build_queue()


st.title("Plant DDN-01 – link review")
q = queue()
todo = pending(q)
done = load_decisions()

with st.sidebar:
    reviewer = st.text_input("Reviewer", value="engineer")
    kinds = st.multiselect("Show", sorted(q.kind.unique()), default=sorted(q.kind.unique()))
    st.metric("Waiting", len(todo[todo.kind.isin(kinds)]))
    st.metric("Decided", len(done))
    st.caption("Auto-accepted links are already in the graph; this queue is the middle confidence band. "
               "Decisions become `method=engineer` edges and training labels on the next run.")

tab_review, tab_done = st.tabs(["Review", "Decisions"])

with tab_review:
    items = todo[todo.kind.isin(kinds)]
    if items.empty:
        st.success("Nothing left to review.")
    else:
        item = items.iloc[0].to_dict()
        st.subheader(f"{item['kind']}: {item['record']}")
        st.write(item["context"])
        a = assets().set_index("functional_location")
        prop = item["proposed_fl"]
        desc = f"{a.at[prop, 'name']} ({a.at[prop, 'asset_type']})" if prop in a.index else ""
        st.info(f"Proposed asset: **{prop}** {desc} — confidence {item['confidence']:.2f}")
        comment = st.text_input("Comment (optional)", key=f"c_{item['item_id']}")
        c1, c2, c3 = st.columns([1, 1, 3])
        if c1.button("Approve", type="primary", key=f"a_{item['item_id']}"):
            save_decision(item, "approve", prop, reviewer, comment)
            st.rerun()
        if c2.button("Reject", key=f"r_{item['item_id']}"):
            save_decision(item, "reject", None, reviewer, comment)
            st.rerun()
        with c3:
            options = assets().functional_location.tolist()
            choice = st.selectbox("…or correct to", options, index=options.index(prop) if prop in options else 0,
                                  key=f"s_{item['item_id']}")
            if st.button("Save correction", key=f"x_{item['item_id']}"):
                save_decision(item, "correct", choice, reviewer, comment)
                st.rerun()
        st.caption(f"{len(items) - 1} more after this one.")

with tab_done:
    st.dataframe(done, width="stretch", hide_index=True)
