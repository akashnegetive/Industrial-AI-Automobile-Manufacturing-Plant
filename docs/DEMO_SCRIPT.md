# 5-minute demo video – script

The assignment asks for: **one robot tag going from raw name to a graph node, and one VIN traced end to
end.** Everything below runs on the laptop after `run_all.bat` has finished (Neo4j running).

**Before recording:**
- Start the Streamlit screen **after** your last `git pull` and `run_all` (a screen started earlier keeps old code in memory).
- Close other windows and make the PowerShell font big (Ctrl + mouse wheel).
- Open these and leave them ready:
  - PowerShell in the project folder, with `$env:PYTHONPATH = "src"` already run;
  - Neo4j Browser at http://localhost:7474, logged in;
  - `streamlit run apps\ask_app.py` running in a second PowerShell, with its browser tab open.
- Don't show your OpenAI key: no `echo $env:OPENAI_API_KEY`, and no settings screens.
- Record with Win + G (Xbox Game Bar) or OBS, with the microphone on.

| Time | Show | Say (in your own words) |
|---|---|---|
| 0:00–0:30 | README "Results" table | "Plant DDN-01: the same equipment has a different name in SAP, the historian, MES, drawings and work orders. This pipeline links them into one knowledge graph with provenance, then uses it for anomaly detection and question answering. It runs with one command." |
| 0:30–2:00 | `.venv\Scripts\python -m ddn.demo tag DDN1_BIW_L2_R07_WELDCUR.PV` | Walk down the 5 blocks: **raw** PI tag (no station in the name, R07 not RB07) → **parsed** (ISA-5.1 `IT`, unit kA) → **matched** to `DDN1-BIW-L2-ST04-RB07`, auto-accepted (rules and ML agree) → **graph edge** with source, method, confidence, status, evidence. Values stay in Parquet (`store_uri`) → **context**: hierarchy to the site, anomaly AN-003, its work order. |
| 2:00–2:30 | Neo4j Browser: `MATCH p=(a:Asset {fl:'DDN1-BIW-L2-ST04-RB07'})-[r]-(x) RETURN p LIMIT 40` | "Here is the same robot in the graph: its time series, work orders, the anomaly, the vehicles it welded." Click one edge to show the provenance properties. |
| 2:30–4:00 | `.venv\Scripts\python -m ddn.demo vin` | "One car end to end." Route through 44 stations (point out any `inferred` passage: a missed RFID read filled from takt time); robots that welded it; torque results; parts and supplier lots; the cold-weld defect → `causedBy` AN-003 on robot RB07 → fixed by WO 4102961. "Every line is one Cypher query." |
| 4:00–4:45 | ask_app: type *"Which robot caused the cold welds on 7 and 8 September, and which work order fixed it?"*, then *"Who was the shift supervisor on 9 September?"* | First: the cited answer; open the Cypher expander ("validated, read-only"). Second: **"I don't know"**. "No citation, no claim." |
| 4:45–5:00 | `reports/14_graphrag.md` header or the report PDF | "Matching F1 1.000 tags / 0.982 work orders, 0 wrong auto-links, 8/8 anomalies, GraphRAG 10/10, and 4/5 on unseen questions. The limits are in the report." |

**If something goes wrong while recording:** stop and start again. Five minutes is short, so two or three
takes is normal. If Neo4j isn't ready yet, wait for `docker compose ps` to show `healthy`.

**Upload:** an unlisted YouTube video or a Google Drive link. Put the link in the README under "Demo video".
