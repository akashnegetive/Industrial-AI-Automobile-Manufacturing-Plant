---
title: "Live demo guide – Plant DDN-01 interview"
---

# Live demo guide

This guide is for the **live demo in the interview** (slide 27, "Live demo: four things to show") plus every query from the slides. Every step has a **DO** box (what to click or type) and a **SAY** box (what to say). Total time is about **12–15 minutes**. If time is short, do only the parts marked ★.

<div class="note"><b>Three golden rules.</b><br>1. <b>Never re-run <code>run_all</code> in the hour before the interview.</b> It clears and reloads Neo4j, and a half-loaded graph returns empty results.<br>2. <b>Do not approve every work order in the review queue.</b> Each approval becomes a confidence-1.0 edge <i>and</i> a training label, so a wrong approval teaches the model a mistake. Approve only the items listed in Part 4, which are checked against the anomaly report.<br>3. <b>Never show your OpenAI key</b> on screen.</div>

## The demo at a glance

| # | What you show | Slide | Time |
|---:|---|---|---|
| ★1 | One robot tag: raw name → graph node (`ddn.demo tag`) | 27, 17 | 2 min |
| 2 | The tag as a picture in Neo4j + its provenance | 17 | 1 min |
| ★3 | One car end to end (`ddn.demo vin`) | 19, 27 | 2 min |
| 4 | The same car as a picture + the defect → cause → work order line | 19 | 1 min |
| ★5 | Review loop: before → approve → after | 14, 15, 27 | 2.5 min |
| 6 | Link prediction suggestion in the review screen | 24 | 1 min |
| ★7 | Ask the plant: cited answer + "I don't know" | 22, 23, 27 | 2 min |
| 8 | Plant questions D3, D5, D7 (+ the others if asked) | 18 | 2–3 min |
| 9 | The three views on one graph | 7, 17 | 1 min |

# Part 1 – The day before (about 20 minutes)

**1.1 Open PowerShell in the project folder:**
```powershell
cd "C:\Users\AKASH\OneDrive\Desktop\akash\Industrial-AI-Automobile-Manufacturing-Plant"
```

**1.2 Start from a clean state.** If you approved anything earlier, move the decisions aside, so the review queue is full again and all tests pass:
```powershell
if (Test-Path data\review\decisions.csv) { move data\review\decisions.csv $HOME\Desktop\decisions_old.csv }
```

**1.3 Start Docker Desktop**, wait until it says "Engine running", then:
```powershell
docker compose up -d
.\run_all.bat
```
Wait for **"All 18 steps done"** and **"102 passed"** (about 11 minutes).

**1.4 Check that nothing differs from GitHub:**
```powershell
git status
```
It should say *"nothing to commit, working tree clean"*.

**1.5 Practise once,** start to end, with a timer. The first try usually takes 20 minutes; that's normal.

# Part 2 – 30 minutes before the interview

**2.1 Start Docker Desktop**, then make sure Neo4j is up (no need to run `run_all`):
```powershell
docker compose up -d
```

**2.2 Window A – demo commands.** Open a new PowerShell:
```powershell
cd "C:\Users\AKASH\OneDrive\Desktop\akash\Industrial-AI-Automobile-Manufacturing-Plant"
$env:PYTHONPATH = "src"
cls
```

**2.3 Window B – Ask the plant.** Open a new PowerShell. Set your key **before you share the screen**, then start the app:
```powershell
cd "C:\Users\AKASH\OneDrive\Desktop\akash\Industrial-AI-Automobile-Manufacturing-Plant"
$env:OPENAI_API_KEY = "paste-your-key-here"
.venv\Scripts\streamlit run apps\ask_app.py --server.port 8501
```
**Minimise window B** and never open it while sharing: the key line is visible in it.

**2.4 Window C – Review screen.** Open a new PowerShell:
```powershell
cd "C:\Users\AKASH\OneDrive\Desktop\akash\Industrial-AI-Automobile-Manufacturing-Plant"
.venv\Scripts\streamlit run apps\review_app.py --server.port 8502
```
Minimise it.

**2.5 Browser tabs, in this order:**

1. `https://github.com/akashnegetive/Industrial-AI-Automobile-Manufacturing-Plant` (README, "Results" table)
2. `http://localhost:7474` – Neo4j (user `neo4j`, password `ddn-plant-2026`)
3. `http://localhost:8501` – Ask the plant
4. `http://localhost:8502` – Review screen
5. Your slides

**2.6 Copy every Cypher query from this guide into a Notepad file**, in order, so you paste them instead of typing.

**2.7 Make it readable:** PowerShell text bigger (Ctrl + mouse wheel), browser zoom 125 % (Ctrl + plus), Windows "Do not disturb" on, close email and chat.

**2.8 Quick health check** in the Neo4j tab:
```cypher
MATCH (n) RETURN count(n) AS nodes
```
Expect **165,706**. If it's much lower, the graph didn't finish loading: see Part 6.

<div class="note"><b>How to run a query in Neo4j:</b> paste it in the top box and press <b>Ctrl + Enter</b> (or the blue play button). For a picture, the query must return paths (<code>p</code>, <code>p1</code>…); switch between <b>Graph</b> and <b>Table</b> with the icons next to the result. Drag circles with the mouse if they overlap. Click a node or a line to see its properties.</div>

# Part 3 – The demo, step by step

## ★ Step 1 – One robot tag: raw name → graph node (slide 27, first box)

<div class="do"><b>DO:</b> Window A. Type and press Enter:</div>

```powershell
.venv\Scripts\python -m ddn.demo tag DDN1_BIW_L2_R07_WELDCUR.PV
```

The output has **5 blocks**. Scroll slowly and point at each one.

<div class="say"><b>SAY (block 1 – raw):</b> "This is a raw historian tag, the weld current of a robot. It says R07, but SAP calls the robot RB07, and the name has no station."<br><br><b>Block 2 – parsed:</b> "My parser splits it into shop BIW, line L2, robot RB07, signal weld current, with the ISA-5.1 code and the unit, kiloamps."<br><br><b>Block 3 – matched:</b> "The matcher, rules plus LightGBM, links it to DDN1-BIW-L2-ST04-RB07. The station ST04 came from the asset master, not from the tag. Confidence 1.0, so it's auto-accepted."<br><br><b>Block 4 – graph edge:</b> "This is the edge in Neo4j. It stores source system, method, confidence, status and evidence. The values aren't in the graph, only a pointer to Parquet."<br><br><b>Block 5 – context:</b> "Now the context: the robot belongs to station 4, line 2, the body shop and the plant. There's anomaly AN-003 on this signal and the work order that fixed it."</div>

**Meaning:** this is contextualization in one example: a meaningless string becomes a node with a place in the hierarchy, a history and provenance.

## Step 2 – The tag as a picture, and its provenance (slide 17)

<div class="do"><b>DO:</b> Neo4j tab. Paste and run:</div>

```cypher
MATCH p1 = (t:TimeSeries {tag: 'DDN1_BIW_L2_R07_WELDCUR.PV'})<-[:hasTimeSeries]-(a:Asset)
MATCH p2 = (a)-[:partOf*1..5]->(:Site)
OPTIONAL MATCH p3 = (t)-[:hasEvent]->(:AnomalyEvent)
OPTIONAL MATCH p4 = (a)-[:hasEvent]->(:AnomalyEvent)
RETURN p1, p2, p3, p4
```

You see: **tag ← robot RB07 → station ST04 → line L2 → body shop → plant**, plus **AN-003** attached to the tag and the robot.

<div class="do"><b>DO:</b> click the line between the tag and the robot to see its properties. Or run this table version (the exact edge on slide 17):</div>

```cypher
MATCH (a:Asset)-[r:hasTimeSeries]->(t:TimeSeries {tag: 'DDN1_BIW_L2_R07_WELDCUR.PV'})
RETURN a.fl AS asset, r.source_system AS source, r.method AS method, r.confidence AS confidence,
       r.status AS status, r.created_at AS created_at, r.evidence AS evidence
```
**Expected:** asset `DDN1-BIW-L2-ST04-RB07`, method `rule`, confidence `1.0`, status `approved`, evidence *"rules (exact) and ML agree"*.

<div class="say"><b>SAY:</b> "This is the ISA-95 hierarchy in the graph. Every edge carries provenance, so 'why does the graph think this?' is a property lookup. That's how I can report zero edges without provenance."</div>

## ★ Step 3 – One car, end to end (slide 19)

<div class="do"><b>DO:</b> Window A. Type <code>cls</code>, Enter, then:</div>

```powershell
.venv\Scripts\python -m ddn.demo vin
```
It picks car **MDDA5XK00D003924** (Hatch 1.2 MT, 8 Sep 2026).

<div class="say"><b>SAY, scrolling the blocks:</b><br>"Its route: 44 stations, body start 08:55 on BIW line 1, end-of-line audit at 20:00. Missed RFID reads are filled from line order and the car's own delay, and marked inferred; I validated that by hiding 5,793 real reads, median error 0.28 minutes."<br>"Machines that worked on it: 40 weld robots, 6 sealer and 10 paint robots, from processedBy edges."<br>"11 torque results, all OK, and 9 parts with their supplier lots, including door-seal lot WS-260904-B."<br>"And the key line: defect D700356, BW-017 weld nugget small, caused by anomaly AN-003 on robot RB07, derived, confidence 0.9, fixed by work order 4102961. The same robot as my first example. Every line is one Cypher query."</div>

## Step 4 – The same car as a picture + the defect line (slide 19)

<div class="do"><b>DO:</b> Neo4j tab, graph picture:</div>

```cypher
MATCH p1 = (v:Vehicle {vin: 'MDDA5XK00D003924'})-[:hasDefect]->(:Defect)-[:causedBy]->(e:AnomalyEvent)<-[:hasEvent]-(:Asset)
MATCH p2 = (v)-[:containsPart]->(:Part {part_no: 'DOOR_SEAL'})-[:fromLot]->(:SupplierLot)
MATCH p3 = (v)-[:exposedTo]->(e)
RETURN p1, p2, p3
```

<div class="do"><b>DO:</b> the exact slide-19 line as a table:</div>

```cypher
MATCH (v:Vehicle)-[:hasDefect]->(d:Defect {defect_id: 'D700356'})
OPTIONAL MATCH (d)-[c:causedBy]->(cause)
OPTIONAL MATCH (eq:Asset)-[:hasEvent]->(cause)
OPTIONAL MATCH (w:WorkOrder {wo_number: cause.confirming_wo})
RETURN v.vin AS vin, d.defect_id AS defect, d.defect_code AS code, d.defect_desc AS description,
       coalesce(cause.anomaly_id, cause.lot_id) AS cause, eq.fl AS equipment,
       c.method AS method, c.confidence AS confidence, w.wo_number AS work_order, w.short_text AS wo_text
```
**Expected:** D700356 · BW-017 · cause AN-003 · DDN1-BIW-L2-ST04-RB07 · derived · 0.9 · 4102961 "R7 gun tip dressing fail, cap changed".

<div class="say"><b>SAY:</b> "One query joins five systems: MES for the car, QMS for the defect, the historian for the signal, SAP for the robot and maintenance for the work order. Before the graph, this needed several exports and a spreadsheet."</div>

## ★ Step 5 – The review loop: before → approve → after (slides 14, 15, 27)

This proves the human-in-the-loop part: only confident or engineer-approved links enter the graph.

**5a. Before.**
<div class="do"><b>DO:</b> Neo4j tab. Run:</div>

```cypher
MATCH (a:Asset)-[r:hasWorkOrder]->(w:WorkOrder {wo_number: '4102964'})
RETURN a.fl AS asset, r.method AS method, r.confidence AS confidence, r.status AS status, r.evidence AS evidence
```
**Expected:** *"no records"*.

<div class="say"><b>SAY:</b> "Work order 4102964 is the NR14 nutrunner calibration. The matcher gave it 0.66, which is the review band, so it's not in the graph yet."</div>

**5b. Approve.**
<div class="do"><b>DO:</b> Review tab (localhost:8502).<br>1. Left sidebar, <b>Reviewer</b>: type your name.<br>2. In <b>Search</b>, type <code>4102964</code>.<br>3. You see an orange box: <i>"This work order is the best explanation found for a detected anomaly"</i>, the work-order text, and <b>Proposed asset: DDN1-ASM-FN1-ST03-NR14 (Nutrunner)</b>, confidence 0.66.<br>4. Read the text aloud ("NR14 transducer calibration – found offset"), then click <b>Approve</b>.<br>5. Optional: click the <b>Decisions</b> tab to show the saved row (your name and the time).</div>

<div class="say"><b>SAY:</b> "The engineer sees the text, the proposed asset and why it's prioritised: it explains anomaly AN-002. The text names NR14 and the proposal is nutrunner 14, so I approve. The decision is saved with my name and the time."</div>

**5c. Write it into the graph.**
<div class="do"><b>DO:</b> Window A:</div>

```powershell
.venv\Scripts\python -m ddn.graph --decisions
```
It prints: `approve: (DDN1-ASM-FN1-ST03-NR14)-[:hasWorkOrder {method: engineer}]->(4102964)`.

**5d. After.**
<div class="do"><b>DO:</b> Neo4j tab: run the 5a query again.</div>

**Expected:** 1 row: `DDN1-ASM-FN1-ST03-NR14` · method **engineer** · confidence **1.0** · status **approved** · evidence "engineer decision in the review screen (…)".

<div class="say"><b>SAY:</b> "Same query, and now the link is there, with method 'engineer'. On the next full run the decision is also a training label, so the model learns from it. And it completes the D3 story: NR14's repair work order is now linked."</div>

**Optional: slide 15's work order (4102961).** Search `4102961` in the review screen. It shows *"[from backlog]"* and the orange anomaly box, with proposed asset **DDN1-BIW-L2-ST04-RB07-WG** (the weld gun of RB07). Approve, then run `--decisions` again.

<div class="say"><b>SAY:</b> "This is slide 15's work order. It scored 0.034, so it was in the backlog, but because it explains anomaly AN-003 the queue pulled it into review and ranked it first."</div>

## Step 6 – Link prediction suggestion (slide 24)

<div class="do"><b>DO:</b> Review tab. Search <code>4100629</code>. The item says <i>"[suggested by link prediction] Station 04 L2 fixture locating pin worn, replaced"</i>, with <b>Proposed asset: DDN1-BIW-L2-ST04-FX</b> and <i>"matcher's guess: DDN1-BIW-L1-CV01 (0.002, backlog)"</i>.</div>

<div class="say"><b>SAY:</b> "The matcher had no good candidate: it guessed a conveyor at 0.002. Link prediction looks at the graph instead: records like this one are already linked to fixtures, so it suggests the L2 station 4 fixture. It's only ever a suggestion for an engineer, never auto-accepted. For 11 of the 16 records the matcher got wrong, the right asset is in its top 3."</div>

<div class="do"><b>DO (optional):</b> click <b>Approve</b>, because the text clearly says "Station 04 L2 fixture". Then show the <b>Backlog (data quality)</b> tab: <i>"52 links scored below the review threshold…"</i>.</div>

## ★ Step 7 – Ask the plant (slides 22, 23)

<div class="do"><b>DO:</b> Ask tab (localhost:8501). Check the caption says <b>Mode: openai</b> (not "offline"). In <b>Question</b>, type and press Enter:</div>

`Which robot caused the cold welds on 7 and 8 September, and which work order fixed it?`

Wait 5–10 seconds and keep talking.

**Expected:** an answer naming **DDN1-BIW-L2-ST04-RB07** and **4102961** (with AN-003), each sentence followed by *"cites: …"*.

<div class="do"><b>DO:</b> open the <b>"Cypher (validated, run read-only)"</b> expander, then <b>"Rows returned"</b>, then <b>"Related facts added from the graph"</b> if it's there.</div>

<div class="say"><b>SAY:</b> "The LLM, gpt-4o at temperature 0, only writes a Cypher query. My code checks it against the ontology: no write keywords, only known labels, relationships, properties and arrow directions. Then it runs in a read-only transaction. The answer can only use these rows, and every sentence must cite IDs that are in them, or it's dropped. No citation, no claim."</div>

<div class="do"><b>DO:</b> second question:</div>

`Who was the shift supervisor on 9 September?`

**Expected:** an orange **"I don't know"** with a reason (the data has no shift or people information).

<div class="say"><b>SAY:</b> "When the data can't answer, it says 'I don't know' instead of guessing. On unseen questions it scored 4 out of 5 after I read the answers myself, and no answer in any run contained an invented fact."</div>

**Spare questions** (from the evaluation set): *"What caused the paint craters on 10 September?"* (AHU-TC2, AN-006) · *"How many vehicles received parts from supplier lot WS-260904-B?"* (1,785) · *"Was the Oven 2 zone 3 over-temperature on 12 September a quality problem?"* (AN-008, false alarm).

## Step 8 – Plant questions D3, D5, D7 (slide 18)

All seven queries with real output are in `reports/12_graph_queries.md` and the report's Appendix A. These versions need **no `:param`**. Times are written with `localdatetime(...)`, because that's how they are stored (without a time zone).

### D3 – Low wheel-nut torque → which tool → its last calibration (Traceability)
```cypher
MATCH (v:Vehicle)-[:hasTorqueResult]->(r:TorqueResult)-[:tightenedBy]->(tool:Tool)
WHERE r.joint_id STARTS WITH 'WHEEL' AND r.status = 'NOK' AND r.attempt = 1
  AND r.timestamp >= localdatetime('2026-08-29T00:00:00')
  AND r.timestamp < localdatetime('2026-09-05T00:00:00')
MATCH (tool)-[:partOf]->(ctrl:Component)-[:partOf]->(nr:Asset)
OPTIONAL MATCH (x:Asset)-[:hasWorkOrder]->(w:WorkOrder {wo_type: 'CAL'})
  WHERE x IN [nr, ctrl] AND w.created_at <= r.timestamp
WITH v, r, tool, nr, w ORDER BY w.created_at DESC
WITH v, r, tool, nr, collect(w)[0] AS last_cal
OPTIONAL MATCH (v)-[:hasTorqueResult]->(re:TorqueResult {joint_id: r.joint_id, attempt: 2})
RETURN v.vin AS vin, r.joint_id AS joint, r.torque_nm AS torque_nm, r.timestamp AS at,
       tool.tool_id AS tool, nr.fl AS nutrunner, last_cal.wo_number AS last_calibration_wo,
       re IS NOT NULL AS re_hit
ORDER BY at
```
**Expected:** 693 NOK first rundowns on 376 cars, **all on TC14 → NR14**, `last_calibration_wo` empty, 38 never re-hit.

**D3b – calibration coverage per nutrunner (Maintenance):**
```cypher
MATCH (n:Equipment {asset_type: 'Nutrunner'})
OPTIONAL MATCH (x:Asset)-[:hasWorkOrder]->(w:WorkOrder {wo_type: 'CAL'})
  WHERE x = n OR (x)-[:partOf]->(n)
WITH n, count(w) AS calibrations_12m, max(w.created_at) AS last_calibration
RETURN n.fl AS nutrunner, calibrations_12m, last_calibration
ORDER BY calibrations_12m, last_calibration
```
**Expected:** the top two rows have 0 calibrations: **NR04 and NR14**.

<div class="say"><b>SAY:</b> "Every bad torque result came from one tool, NR14, and the graph shows it had no calibration work order in 12 months, one of only two out of twenty. The 'calibration due' alarm fires on every nutrunner, so nobody noticed. The decision for the plant: a calibration plan."</div>

### D5 – Recall scope for the suspect door-seal lot (Traceability)
```cypher
MATCH (l:SupplierLot {lot_id: 'WS-260904-B'})<-[:fromLot]-(:Part)<-[c:containsPart]-(v:Vehicle)
OPTIONAL MATCH (v)-[:hasDefect]->(d:Defect) WHERE d.defect_code = 'WL-104'
WITH l, v, c, count(d) > 0 AS leaked
RETURN l.lot_id AS lot, l.supplier AS supplier, date(c.fitted_at) AS fitted_on,
       count(v) AS vehicles, sum(CASE WHEN leaked THEN 1 ELSE 0 END) AS with_door_leak
ORDER BY fitted_on
```
**Expected:** 4 Sep: 293 cars, 0 leaks · 8 Sep: 593 / 31 · 9 Sep: 597 / 33 · 10 Sep: 302 / 21. Total 1,785.

<div class="say"><b>SAY:</b> "By lot id alone, 1,785 cars. But the 4 September session had zero leaks: the lot id wasn't updated at the station. Using fitting time, the scope is 1,492 cars, which spares 293 good cars from a recall."</div>

### D7 – Plant head: cars at risk vs caught by inspection (Quality)
```cypher
CALL () {
  MATCH (v:Vehicle)-[:hasTorqueResult]->(r:TorqueResult {status: 'NOK', attempt: 1})
  WHERE r.joint_id STARTS WITH 'WHEEL'
    AND NOT EXISTS { (v)-[:hasTorqueResult]->(:TorqueResult {joint_id: r.joint_id, attempt: 2}) }
  RETURN DISTINCT v, 'wheel nut NOK, never re-hit' AS risk, ['AU-077'] AS catches
  UNION
  MATCH (v:Vehicle)-[c:containsPart]->(:Part)-[:fromLot]->(:SupplierLot {lot_id: 'WS-260904-B'})
  WHERE c.fitted_at >= localdatetime('2026-09-08T00:00:00')
  RETURN DISTINCT v, 'door seal from suspect lot' AS risk, ['WL-104'] AS catches
  UNION
  MATCH (v:Vehicle)-[p:processedBy]->(:Asset {fl: 'DDN1-PNT-SL-ST02-SR03'})
  WHERE p.start >= localdatetime('2026-09-09T06:04:00')
    AND p.start <= localdatetime('2026-09-09T10:18:00')
  RETURN DISTINCT v, 'sealed while SR03 nozzle was cold' AS risk, ['WL-101'] AS catches
  UNION
  MATCH (v:Vehicle)-[p:processedBy]->(:Asset {fl: 'DDN1-BIW-L2-ST04-RB07'})
  WHERE p.start >= localdatetime('2026-09-07T13:17:00')
    AND p.start <= localdatetime('2026-09-08T15:09:00')
  RETURN DISTINCT v, 'welded while R07 current was low' AS risk, ['BW-017'] AS catches
}
OPTIONAL MATCH (v)-[:hasDefect]->(d:Defect) WHERE d.defect_code IN catches
WITH risk, v, count(d) > 0 AS caught
RETURN risk, count(v) AS vehicles_at_risk,
       sum(CASE WHEN caught THEN 1 ELSE 0 END) AS caught_by_inspection,
       sum(CASE WHEN caught THEN 0 ELSE 1 END) AS not_caught
ORDER BY vehicles_at_risk DESC
```
**Expected:** door seal 1,492 at risk / 85 caught · cold welds 647 / 103 · cold sealer 106 / 36 · wheel nut never re-hit 37 / 37.

<div class="say"><b>SAY:</b> "This is the plant head's question: how many cars carried a known risk, and how many did inspection catch? For the door-seal lot, 1,492 cars at risk and only 85 caught: the shower test doesn't see every bad seal. The 'not caught' column is the field risk."</div>

### Backup queries (only if asked)

**D1 – Oven 2 temperature sensors (Maintenance):**
```cypher
MATCH path = (a:Asset)-[:partOf*0..3]->(:Asset {fl: 'DDN1-PNT-OV2'})
WITH a, relationships(path) AS rels WHERE all(x IN rels WHERE x.valid_to IS NULL)
MATCH (a)-[:hasTimeSeries]->(t:TimeSeries {isa51_code: 'TT'})
OPTIONAL MATCH (a)-[:hasWorkOrder]->(w:WorkOrder)
WITH a, t, collect(w) AS wos
RETURN a.fl AS equipment, t.tag AS sensor, t.unit AS unit_in_source, t.unit_canonical AS unit,
       round(t.latest_value, 1) AS latest_value,
       [w IN wos WHERE w.closed_at IS NULL
                    OR w.closed_at > localdatetime('2026-09-15T00:00:00') | w.wo_number] AS open_work_orders,
       size(wos) AS work_orders_12m
ORDER BY equipment, sensor
```
**Expected:** 4 sensors (zones Z1–Z4), degF in the source, stored as degC, no open work orders (all closed in the export). *Meaning:* the unit fix and the variable-length `partOf*0..3` path.

**D2 – Water-leak car → sealer robots and their signals (Quality):**
```cypher
MATCH (v:Vehicle {vin: 'MDDA5XK0XD004375'})-[:hasDefect]->(d:Defect)
WHERE d.defect_family = 'water leak'
MATCH (v)-[p:processedBy]->(e:Asset) WHERE e.asset_type IN ['SealerRobot', 'Dispenser']
OPTIONAL MATCH (e)-[:hasTimeSeries]->(t:TimeSeries) WHERE t.store_uri IS NOT NULL
RETURN v.vin AS vin, d.defect_code + ' ' + d.location AS defect, e.fl AS equipment,
       p.start AS start, p.inferred AS passage_inferred, p.confidence AS edge_confidence,
       t.tag AS signal, t.store_uri AS store_uri
ORDER BY equipment, signal
```
*Meaning:* the SR03 pass is **inferred** (reader offline, confidence 0.85). The graph gives the `store_uri`, and Python reads the values from Parquet: the SR03 nozzle was at **38.3–39.4 °C** against a 45 °C set point.

**D4 – Paint craters → upstream equipment (Quality):**
```cypher
MATCH (insp:Asset {fl: 'DDN1-PNT-INSP-ST01'})<-[:feeds*1..3]-(u:Asset)
OPTIONAL MATCH (e:Asset)-[:partOf*0..2]->(u)
WITH DISTINCT u, e
OPTIONAL MATCH (al:Alarm)-[:raisedBy]->(e)
  WHERE al.event_time >= localdatetime('2026-09-10T14:00:00')
    AND al.event_time <= localdatetime('2026-09-10T17:00:00') AND NOT al.is_duplicate
RETURN u.fl AS upstream, count(DISTINCT al) AS alarms, collect(DISTINCT al.code) AS alarm_codes
ORDER BY alarms DESC
```
**Expected:** **DDN1-PNT-AHU-AHUTC2 first, 184 alarms** (H-07, H-15). *Meaning:* `feeds*1..3` walks up to 3 steps upstream, the same idea as TwinMaker's variable-length paths.

**D6 – What is not linked yet (Maintenance):**
```cypher
CALL () { MATCH (t:TimeSeries) WHERE NOT ()-[:hasTimeSeries]->(t)
          RETURN 'tag' AS kind, count(t) AS unlinked, collect(t.tag)[..5] AS examples }
RETURN kind, unlinked, examples
UNION ALL
CALL () { MATCH (w:WorkOrder) WHERE NOT ()-[:hasWorkOrder]->(w)
          RETURN 'work order' AS kind, count(w) AS unlinked,
                 collect(w.wo_number + ' ' + w.short_text)[..5] AS examples }
RETURN kind, unlinked, examples
```
**Expected on a fresh run:** 9 tags and 122 work orders: exactly the review band plus the backlog. Each approval in the demo lowers the work-order count by one. *Meaning:* the graph honestly shows what isn't linked.

**E1 – All 8 anomalies with context (Quality):**
```cypher
MATCH (eq:Asset)-[:hasEvent]->(e:AnomalyEvent)
OPTIONAL MATCH (v:Vehicle)-[:exposedTo]->(e)
OPTIONAL MATCH (d:Defect)-[:causedBy]->(e)
OPTIONAL MATCH (w:WorkOrder {wo_number: e.confirming_wo})
RETURN e.anomaly_id AS id, eq.fl AS equipment, e.judged AS verdict,
       count(DISTINCT v) AS vehicles_exposed, count(DISTINCT d) AS defects_caused,
       w.wo_number + ' ' + w.short_text AS work_order
ORDER BY id
```
**Expected:** AN-001 … AN-008. For example AN-003: 663 cars exposed, 103 defects, WO 4102961; AN-008: false_alarm.

## Step 9 – Three views on one graph (slides 7 and 17)

<div class="say"><b>SAY first:</b> "Like Cognite, I separate storage from views. The ontology defines three views: Maintenance, Quality and Traceability. Same nodes and edges, different starting point."</div>

**Maintenance – start from a machine:**
```cypher
MATCH (eq:Asset {fl: 'DDN1-BIW-L2-ST04-RB07'})
OPTIONAL MATCH p1 = (eq)-[:hasTimeSeries]->(:TimeSeries)
OPTIONAL MATCH p2 = (eq)-[:hasWorkOrder]->(:WorkOrder)-[:reportsFailure]->(:FailureMode)
RETURN eq, p1, p2 LIMIT 40
```
**Quality – start from an anomaly:**
```cypher
MATCH p = (:Vehicle)-[:hasDefect]->(:Defect)-[:causedBy]->(e:AnomalyEvent {anomaly_id: 'AN-003'})<-[:hasEvent]-(:Asset)
RETURN p LIMIT 25
```
**Traceability – start from a supplier lot:**
```cypher
MATCH p = (:Vehicle)-[:containsPart]->(:Part)-[:fromLot]->(l:SupplierLot {lot_id: 'WS-260904-B'})
RETURN p LIMIT 25
```
Then show `docs/ontology.md` on GitHub, section *"Containers and views (Cognite mapping)"*.

<div class="say"><b>If asked "is it enforced?":</b> "Here the views are a design contract: defined in the ontology, validated, and used to organise the queries. They're not access control; Neo4j Community has no per-role security. In production I'd use Cognite's managed views, or Neo4j Enterprise roles per view."</div>

# Part 4 – Which work orders to approve (and why not all)

On a fresh run the review queue holds **70 work orders, 9 tags and 44 document links**, plus link-prediction items for the **52 backlog** work orders. The full work-order list is in the appendix.

## Safe to approve in the demo (checked against the anomaly report)

| Search | Proposed asset | Text (short) | Why it's correct |
|---|---|---|---|
| **4102964** | DDN1-ASM-FN1-ST03-NR14 | NR14 transducer calibration – found offset | text names NR14; confirms AN-002 |
| **4102961** | DDN1-BIW-L2-ST04-RB07-WG | R7 gun tip dressing fail, cap changed (L2 ST4 robot 7) | weld gun of RB07; confirms AN-003 |
| 4102963 | DDN1-PNT-AHU-AHUTC2-HUM | AHU TC2 humidifier valve stuck open | humidifier of AHU-TC2; confirms AN-006 |
| 4102967 | DDN1-PNT-AHU-AHUTC1-SF | AHU TC1 supply fan bearing noise, DE bearing replaced | supply fan of AHU-TC1; confirms AN-005 |
| 4100629 | DDN1-BIW-L2-ST04-FX (link prediction) | Station 04 L2 fixture locating pin worn | text names L2, station 04, fixture |
| 4102478 | DDN1-BIW-L1-ST07-TD (link prediction) | tip dresser Station 07 L1 blade broken | text names L1, station 07, tip dresser |
| 4100244 | DDN1-PRS-PL1-DST (link prediction) | PL1 DST jam, cleared | text names press line 1 destacker |

**Always read the text on screen first.** If the proposed asset doesn't match the text, don't approve.

## Why not approve all 70?

- Many proposals are **ambiguous**: "R7 dress pack cable damaged" (robot 7 exists on three lines), "WG water leak at cap adaptor" (no robot named at all), or a robot vs its own weld gun. That ambiguity is exactly why they're in review.
- An approval becomes a **confidence-1.0 `engineer` edge** and a **training label**. A wrong approval puts a false fact in the graph *and* teaches the model the mistake.
- In the interview, say: *"I approve only what the text confirms. Everything else stays in review for the engineer who knows the line."*

## Showing Correct and Reject (optional)

- **Correct:** search `4100787` ("L1 ST03 robo tip dress fail, cutter blade changed"). Link prediction proposes the station `DDN1-BIW-L1-ST03`. The cutter blade belongs to the tip dresser, so pick **DDN1-BIW-L1-ST03-TD** in *"…or correct to"* and click **Save correction**.
- **Reject:** use it on an item whose proposed asset clearly contradicts the text. Click **Reject**: the record stays unlinked and isn't suggested again.

# Part 5 – After the interview: back to a clean state

Approvals change the next run: approved work orders become training labels, leave the review queue, and **one test then fails** (`test_review_queue_pulls_anomaly_work_orders…`). That's the feedback loop working; the test assumes nothing was reviewed yet. To get back to 102 passed:
```powershell
move data\review\decisions.csv $HOME\Desktop\decisions_demo.csv
.\run_all.bat
```
If you'd rather keep the decisions, keep the file: everything still works, and only that one test fails.

# Part 6 – If something goes wrong

| Problem | Fix |
|---|---|
| Neo4j queries return nothing | The graph is still loading or empty. Run `MATCH (n) RETURN count(n)`: expect 165,706. If it's lower, wait for `run_all` to finish |
| Only the Quality / anomaly queries are empty | Anomaly data is loaded last. Wait for the run to finish |
| A query with a date returns nothing | Use `localdatetime('…')`, not `datetime('…')` or plain text: times are stored without a time zone |
| `ddn.demo` can't connect | Docker Desktop isn't running: start it, `docker compose up -d`, wait 1 minute |
| `No module named ddn` | Window A is missing `$env:PYTHONPATH = "src"` |
| Ask screen says "Mode: offline" | The key isn't set in window B: close it, open a new PowerShell, set the key, start Streamlit again |
| The answer takes long | Normal: 5–10 s per question. Keep talking |
| Review search shows "Nothing left to review" | That item is already decided. Check the **Decisions** tab, or use another item from Part 4 |
| Step 5a already shows a row | 4102964 was approved before. Use 4102963 or 4102967 and change the number in the query |
| Something breaks live | Stay calm and say: "Let me show the recorded version." Open the video: youtu.be/86zMkBF6CfI |

# Appendix – All work orders waiting for a person

From `outputs/predictions_workorder_to_asset.csv` on a fresh run. **Review band: 70**, **backlog: 52** (backlog items appear in the review screen only with a link-prediction suggestion, or when they explain an anomaly). The work-order text is shown in the review screen; read it before deciding. ⚑ = explains an anomaly.

**Review band (70)**

| WO | Proposed asset | Conf. | WO | Proposed asset | Conf. |
|---|---|---:|---|---|---:|
| 4100969 | `DDN1-ASM-TR1-ST05-NR03` | 0.930 | 4100733 | `DDN1-BIW-L2-ST02-RB04` | 0.522 |
| 4101050 | `DDN1-BIW-L1-ST06-RB12` | 0.921 | 4100848 | `DDN1-BIW-L1-ST08-RB16` | 0.493 |
| 4102521 | `DDN1-PRS-PL2-PR2-MTR` | 0.920 | 4102240 | `DDN1-BIW-L1-ST01-RB01-WG` | 0.491 |
| 4100304 | `DDN1-PNT-AHU-AHUTC1-SF` | 0.920 | 4102044 | `DDN1-PNT-OV1-Z1-FAN` | 0.491 |
| 4102692 | `DDN1-UTL-CMP01` | 0.914 | 4102348 | `DDN1-BIW-L1-ST08-RB16` | 0.460 |
| 4100865 | `DDN1-PNT-OV1-Z3` | 0.906 | 4101971 | `DDN1-BIW-L1-ST07-RB14` | 0.460 |
| 4102637 | `DDN1-PNT-OV1-Z4-BR` | 0.904 | 4101598 | `DDN1-BIW-L1-ST04-RB08` | 0.457 |
| 4102921 | `DDN1-PNT-OV1-Z2` | 0.896 | 4101268 | `DDN1-PRS-PL1-PR5` | 0.433 |
| 4101212 | `DDN1-ASM-TR2-ST01-NR05` | 0.890 | 4101088 | `DDN1-BIW-L1-ST04-RB07-WG` | 0.427 |
| 4101350 | `DDN1-BIW-L1-ST03-RB06` | 0.885 | 4101856 | `DDN1-BIW-L1-ST01-RB02-WG` | 0.395 |
| 4101928 | `DDN1-BIW-L2-ST02-FX` | 0.885 | 4101143 | `DDN1-BIW-L1-ST07-RB13` | 0.390 |
| 4100279 | `DDN1-ASM-TR1-ST02-NR02-TC` | 0.880 | 4100451 | `DDN1-BIW-L1-ST08-RB16` | 0.381 |
| 4102128 | `DDN1-ASM-TR1-ST02-NR02-TC` | 0.880 | 4100391 | `DDN1-BIW-L1-CV01` | 0.376 |
| 4101418 | `DDN1-ASM-TR1-ST02-NR02-TC` | 0.880 | 4100978 | `DDN1-ASM-TR1-ST05-NR03-TC` | 0.374 |
| 4100960 | `DDN1-PNT-AHU-AHUTC2-EF` | 0.866 | 4102403 | `DDN1-BIW-L1-ST04-RB08-WG` | 0.365 |
| 4101354 | `DDN1-PNT-OV2-Z4-BR` | 0.864 | ⚑ 4102967 | `DDN1-PNT-AHU-AHUTC1-SF` | 0.362 |
| 4101249 | `DDN1-ASM-CH1-ST02-NR08` | 0.837 | 4101324 | `DDN1-PRS-PL1-PR1-LUB` | 0.361 |
| 4101426 | `DDN1-BIW-L2-ST02-RB04-WG` | 0.836 | 4101103 | `DDN1-PNT-OV2-Z2-FAN` | 0.353 |
| 4102758 | `DDN1-ASM-TR1-ST05-NR03` | 0.831 | 4100385 | `DDN1-BIW-L2-ST04-FX` | 0.346 |
| 4102926 | `DDN1-BIW-L1-ST04-RB07` | 0.820 | 4100443 | `DDN1-BIW-L1-ST04-RB07` | 0.340 |
| 4102927 | `DDN1-BIW-L3-ST03-RB05` | 0.812 | 4101515 | `DDN1-BIW-L1-ST03-RB06-WG` | 0.333 |
| 4101536 | `DDN1-BIW-L2-ST05-RB09` | 0.804 | 4101872 | `DDN1-BIW-L1-ST01-RB02` | 0.319 |
| 4102882 | `DDN1-PRS-PL1-PR3-HOL` | 0.763 | 4102357 | `DDN1-BIW-L1-ST02-RB03` | 0.314 |
| 4101187 | `DDN1-BIW-L3-ST04-RB07-WG` | 0.748 | 4102867 | `DDN1-BIW-L1-ST03-RB05-WG` | 0.245 |
| 4101218 | `DDN1-ASM-TR1-ST02-NR02` | 0.748 | 4101736 | `DDN1-PNT-EDO-Z3-FAN` | 0.234 |
| 4101534 | `DDN1-BIW-L3-ST03-RB05` | 0.743 | 4100545 | `DDN1-ASM-TR2-ST01-NR04-TC` | 0.218 |
| 4100509 | `DDN1-BIW-L3-CV01` | 0.731 | 4102262 | `DDN1-PRS-PL2-DST` | 0.211 |
| 4100022 | `DDN1-BIW-L1-ST02-RB04` | 0.730 | 4100963 | `DDN1-BIW-L1-ST01-RB01` | 0.202 |
| 4101250 | `DDN1-PNT-AHU-AHUTC1-SF` | 0.717 | 4100321 | `DDN1-PRS-PL2-PR2-HOL` | 0.165 |
| ⚑ 4102964 | `DDN1-ASM-FN1-ST03-NR14` | 0.663 | 4100745 | `DDN1-BIW-L1-ST08-RB15-WG` | 0.164 |
| 4102142 | `DDN1-BIW-L1-ST01-RB02` | 0.568 | 4101416 | `DDN1-BIW-L1-ST07-TD` | 0.160 |
| 4101041 | `DDN1-BIW-L3-ST01-RB02` | 0.541 | ⚑ 4102963 | `DDN1-PNT-AHU-AHUTC2-HUM` | 0.139 |
| 4101491 | `DDN1-BIW-L1-ST07-RB14` | 0.529 | 4102173 | `DDN1-PNT-EDO-Z1-FAN` | 0.139 |
| 4100468 | `DDN1-BIW-L1-ST07-RB13` | 0.529 | 4100050 | `DDN1-BIW-L2-ST04-RB08-WG` | 0.130 |
| 4102702 | `DDN1-BIW-L2-ST06-RB11-WG` | 0.523 | 4101124 | `DDN1-ASM-FN1-ST06-NR19-TC` | 0.102 |

**Backlog (52)**

| WO | Proposed asset | Conf. | WO | Proposed asset | Conf. |
|---|---|---:|---|---|---:|
| 4100382 | `DDN1-BIW-L1-ST01-RB01-WG` | 0.086 | 4102897 | `DDN1-PNT-OV2-Z1-FAN` | 0.010 |
| 4101732 | `DDN1-BIW-L1-ST01-RB02` | 0.058 | 4101259 | `DDN1-ASM-EOL-WT-RIG` | 0.009 |
| 4102821 | `DDN1-BIW-L1-ST06-RB11-WG` | 0.058 | 4100215 | `DDN1-BIW-L3-ST03-RB06` | 0.009 |
| 4101873 | `DDN1-PNT-OV1-Z3-FAN` | 0.058 | 4102082 | `DDN1-BIW-L1-ST01-RB02` | 0.007 |
| 4100380 | `DDN1-BIW-L3-ST03-TD` | 0.053 | 4101360 | `DDN1-BIW-L1-ST02-RB03-WG` | 0.007 |
| 4100363 | `DDN1-BIW-L3-ST03-TD` | 0.053 | 4102722 | `DDN1-BIW-L1-ST02-RB03-WG` | 0.007 |
| 4100906 | `DDN1-BIW-L1-ST02-RB04` | 0.050 | 4101801 | `DDN1-BIW-L2-ST05-RB09-WG` | 0.006 |
| 4101288 | `DDN1-BIW-L1-ST05-RB09` | 0.045 | 4102478 | `DDN1-ASM-CH1-AGV06` | 0.003 |
| 4102271 | `DDN1-BIW-L1-ST02-RB04` | 0.045 | 4100244 | `DDN1-PRS-PL1-PR1` | 0.003 |
| 4100439 | `DDN1-BIW-L1-ST01-FX` | 0.043 | 4100787 | `DDN1-BIW-L1-ST03-RB05` | 0.003 |
| 4100458 | `DDN1-BIW-L1-ST01-FX` | 0.043 | 4102777 | `DDN1-BIW-L3-ST01-RB01-WG` | 0.002 |
| 4101552 | `DDN1-PNT-AHU-AHUPR` | 0.040 | 4101770 | `DDN1-PNT-OV1-Z1-FAN` | 0.002 |
| ⚑ 4102961 | `DDN1-BIW-L2-ST04-RB07-WG` | 0.034 | 4100940 | `DDN1-PNT-OV1-Z1-FAN` | 0.002 |
| 4100401 | `DDN1-PNT-OV1-Z1-BR` | 0.030 | 4100629 | `DDN1-BIW-L1-CV01` | 0.002 |
| 4100394 | `DDN1-BIW-L1-ST05-RB09-WG` | 0.023 | 4100703 | `DDN1-PNT-AHU-AHUPR-HUM` | 0.002 |
| 4102944 | `DDN1-BIW-L1-ST04-RB07` | 0.022 | 4102231 | `DDN1-PNT-EDO-Z1-BR` | 0.001 |
| 4100639 | `DDN1-BIW-L3-ST02-RB04` | 0.022 | 4100701 | `DDN1-BIW-L3-ST03-TD` | 0.001 |
| 4102036 | `DDN1-BIW-L1-ST05-TD` | 0.021 | 4100324 | `DDN1-PNT-AHU-AHUTC1` | 0.001 |
| 4102314 | `DDN1-BIW-L2-ST02-TD` | 0.021 | 4102854 | `DDN1-BIW-L3-ST01-FX` | 0.001 |
| 4102847 | `DDN1-BIW-L1-ST06-FX` | 0.018 | 4102137 | `DDN1-PNT-PT-T101-P101-MTR` | 0.001 |
| 4101538 | `DDN1-PRS-PL2-PR2-HOL` | 0.017 | 4102282 | `DDN1-BIW-L1-ST01-RB01-WG` | 0.001 |
| 4102406 | `DDN1-BIW-L1-ST08-RB15` | 0.015 | 4101501 | `DDN1-PNT-AHU-AHUPR-SF` | 0.001 |
| 4101320 | `DDN1-BIW-L1-ST07-RB13` | 0.013 | 4100167 | `DDN1-BIW-L1-ST01-RB01-WG` | 0.000 |
| 4101898 | `DDN1-BIW-L2-ST08-RB15` | 0.012 | 4100105 | `DDN1-ASM-FN1-ST03-NR15` | 0.000 |
| 4102636 | `DDN1-BIW-L2-ST02-RB04-WG` | 0.012 | 4102224 | `DDN1-BIW-L1-ST01-RB01-WG` | 0.000 |
| 4102755 | `DDN1-BIW-L1-ST06-TD` | 0.010 | 4102446 | `DDN1-BIW-L2-ST01-RB01-WG` | 0.000 |
