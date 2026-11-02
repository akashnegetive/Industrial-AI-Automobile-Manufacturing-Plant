"""Ask the plant (Part E2): a question box over the knowledge graph.

    streamlit run apps/ask_app.py          (Windows: .venv\\Scripts\\streamlit run apps\\ask_app.py)

Uses the provider chosen by ddn.graphrag.get_provider() (OPENAI_API_KEY -> OpenAI, else offline templates).
Shows the answer with citations, the Cypher that produced it and the raw rows, so every claim can be checked.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ddn import graphrag as G  # noqa: E402

st.set_page_config(page_title="DDN-01 ask the plant", layout="wide")
st.title("Plant DDN-01 – ask the plant")

provider = G.get_provider()
st.caption(f"Mode: **{provider.name if provider else 'offline (templates, no LLM)'}** · "
           f"today = {G.TODAY:%a %d %b %Y} · data 1–14 Sep 2026 · read-only queries · no citation, no claim")

examples = [q for q, *_ in G.EVAL]
pick = st.selectbox("Example questions", [""] + examples)
question = st.text_input("Question", value=pick)

if question:
    with st.spinner("Querying the graph…"):
        a = G.ask(question, provider)
    if a.dont_know:
        st.warning(f"I don't know. {a.reason}")
    else:
        for s in a.sentences:
            st.markdown(f"- {s['text']}  \n  <small>cites: {', '.join(f'`{c}`' for c in s['citations'])}</small>",
                        unsafe_allow_html=True)
        if a.dropped_sentences:
            st.caption(f"{a.dropped_sentences} sentence(s) removed because their citations were not in the data.")
    if a.cypher:
        with st.expander("Cypher (validated, run read-only)"):
            st.code(a.cypher, language="cypher")
    if a.rows:
        with st.expander(f"Rows returned ({len(a.rows)})"):
            st.dataframe(pd.DataFrame(a.rows).astype(str), hide_index=True, width="stretch")
