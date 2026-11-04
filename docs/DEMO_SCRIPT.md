# Demo video – step-by-step guide (5 minutes)

**What the assignment asks for:** "a 5-minute demo video: one robot tag going from raw name to a graph node,
and one VIN traced end to end." Those two stories are the core of the video. The rest (graph browser, question
box, review screen) is a short bonus if time allows.

**The plan, scene by scene:**

| Time | Scene | Must have? |
|---|---|---|
| 0:00–0:25 | 1. Intro: what the project is | yes |
| 0:25–1:35 | 2. One robot tag: raw name → graph node | **yes (required)** |
| 1:35–2:00 | 3. The same robot in the Neo4j graph | nice |
| 2:00–3:20 | 4. One VIN traced end to end | **yes (required)** |
| 3:20–4:20 | 5. Ask the plant: a cited answer and "I don't know" | nice |
| 4:20–4:45 | 6. Review screen: backlog and link prediction | nice (skip if you're short of time) |
| 4:45–5:00 | 7. Closing | yes |

Speak slowly; about 130 words a minute is fine. The script below is about 600 words. Use your own words if
they come more naturally; the script is a guide, not something to read word for word.

---

## Part 1 – Prepare (do this once, about 30 minutes)

### 1.1 Install a screen recorder
You need a recorder that captures **the whole screen** (you'll switch between PowerShell and the browser) and
**your microphone**.

- **Recommended: OBS Studio** (free): https://obsproject.com → Download → Windows → install with defaults.
  1. Open OBS. If the "Auto-Configuration Wizard" appears, choose **"Optimize for recording"** → Next → Next →
     Apply.
  2. In the **Sources** box (bottom), click **+** → **Display Capture** → OK → OK. Your screen appears in OBS.
  3. In the **Audio Mixer** box, speak and check that the **Mic/Aux** bar moves. If not: Settings → Audio →
     Mic/Auxiliary Audio → choose your microphone.
  4. Settings → Output → **Recording Format: mp4** → OK.
  5. Do a 10-second test: **Start Recording**, say "test", **Stop Recording**. Then File → **Show
     Recordings** and play the file. Check you can hear yourself and read the text.
- Easier alternative: **Clipchamp** (built into Windows 11): Start → Clipchamp → Create a new video → Record &
  create → Screen. It records the screen with your mic.
- Don't use Win + G (Xbox Game Bar): it records **one window only**, so switching to the browser won't be recorded.

### 1.2 Make the screen readable
- Close everything else: email, chat, notifications. Turn on **Do not disturb** (Windows: Settings → System →
  Notifications → Do not disturb).
- PowerShell: make the text bigger with **Ctrl + mouse wheel** until about 20 lines fit on the screen. Make the
  window **wide** (maximised), so long lines don't wrap.
- Browser: zoom to **125%** (Ctrl + plus) so the text is readable in the video.
- **Never show your OpenAI key.** Don't type `echo $env:OPENAI_API_KEY` and don't open any settings screens.

### 1.3 Make sure everything is up to date and running
In PowerShell, in the project folder:
```powershell
git pull
.\run_all.bat
```
Wait until it says **"All 18 steps done"** and **"102 passed"**. Docker Desktop must be running; Neo4j stays on
after this.

---

## Part 2 – Open these windows before you press record (5 minutes)

You'll use **3 PowerShell windows** and **3 browser tabs**. Open them all now, so you don't type setup
commands during the video.

**PowerShell window A (for the demo commands):**
```powershell
cd C:\Users\AKASH\OneDrive\Desktop\akash\Industrial-AI-Automobile-Manufacturing-Plant
$env:PYTHONPATH = "src"
cls
```
Leave it empty, ready to type.

**PowerShell window B (question box):**
```powershell
cd C:\Users\AKASH\OneDrive\Desktop\akash\Industrial-AI-Automobile-Manufacturing-Plant
.venv\Scripts\streamlit run apps\ask_app.py
```
A browser tab opens at http://localhost:8501. Leave window B running; just minimise it.

**PowerShell window C (review screen):**
```powershell
cd C:\Users\AKASH\OneDrive\Desktop\akash\Industrial-AI-Automobile-Manufacturing-Plant
.venv\Scripts\streamlit run apps\review_app.py --server.port 8502
```
A browser tab opens at http://localhost:8502. Minimise window C.

**Browser tabs, in this order:**
1. **GitHub README:** https://github.com/akashnegetive/Industrial-AI-Automobile-Manufacturing-Plant (scroll so
   the "Results" table is visible).
2. **Neo4j Browser:** http://localhost:7474. Log in (user `neo4j`, password `ddn-plant-2026`). Paste this query
   into the top box but **don't run it yet**:
   ```cypher
   MATCH p = (a:Asset {fl: 'DDN1-BIW-L2-ST04-RB07'})-[r]-(x)
   WHERE NOT x:Vehicle
   RETURN p LIMIT 30
   ```
   (`NOT x:Vehicle` hides the hundreds of cars, so the picture stays readable.)
3. **Ask the plant:** http://localhost:8501
4. **Review screen:** http://localhost:8502

Important: start both Streamlit screens **after** your last `git pull`. A screen started earlier keeps old
code in memory.

**Practise once without recording.** Run through all 7 scenes with a timer. It's normal for the first try to
take 7 minutes; cut words, not scenes.

---

## Part 3 – Record (scene by scene)

Press **Start Recording** in OBS. Wait 2 seconds, then start talking.

### Scene 1 – Intro (0:00–0:25)
**Show:** browser tab 1, the README "Results" table.

**Say:**
> "Hi, I'm Akash. This is my take-home project for Plant DDN-01. In a car plant, the same machine has a
> different name in SAP, in the historian, in MES, on the drawings and in the work orders. My pipeline links all
> of them to one asset and loads them into a knowledge graph, with the source and confidence on every link. It
> runs with one command. I'll show one robot tag and one car, end to end."

**Point at** (move the mouse over it): the F1 1.000 / 0.982 line.

### Scene 2 – One robot tag: raw name → graph node (0:25–1:35)
**Do:** switch to PowerShell window A. Type and press Enter:
```powershell
.venv\Scripts\python -m ddn.demo tag DDN1_BIW_L2_R07_WELDCUR.PV
```
The output has 5 blocks. Scroll slowly and talk about each one.

**Say:**
> "Block 1 is the raw historian tag: DDN1_BIW_L2_R07_WELDCUR. Notice that it has no station in the name, and it
> says R07, while SAP calls the robot RB07."

> "Block 2: my parser splits it into shop BIW, line L2, robot RB07, signal weld current. The ISA-5.1 code is IT,
> a current, in kiloamps."

> "Block 3: the matcher (rules plus a LightGBM model) links it to DDN1-BIW-L2-ST04-RB07. The station ST04 came
> from the asset master, not from the tag. The confidence is 1.0, so it was auto-accepted."

> "Block 4 is the edge in the graph. Every edge says where it came from: source system, method, confidence,
> status, and the evidence ('rules and ML agree'). The actual values are not in the graph; it only stores a
> pointer to the Parquet file."

> "Block 5 is the context: the robot belongs to station 4, line 2, body shop, plant. There's an anomaly on this
> signal, AN-003, and the work order that fixed it."

### Scene 3 – The same robot in the graph (1:35–2:00)
**Do:** switch to browser tab 2 (Neo4j). Press the **blue play button** (or Ctrl + Enter). A small network
appears. **Click one line (edge)** between the robot and its time series; the properties appear on the right.

**Say:**
> "Here is the same robot in Neo4j: its time series, work orders, the anomaly. If I click an edge, you see the
> provenance: method, confidence, status. So anyone can ask 'why does the graph think this?'"

### Scene 4 – One VIN traced end to end (2:00–3:20)
**Do:** switch to PowerShell window A. Type `cls` and Enter, then:
```powershell
.venv\Scripts\python -m ddn.demo vin
```

**Say**, scrolling through the 6 blocks:
> "Now one car, MDDA5XK00D003924, built on 8 September."

> "Block 1: its route. It passed 44 stations, from the body shop at 08:55 to the final audit at 20:00. If an
> RFID read was missed, the pipeline fills it in from the line sequence and takt time, and marks it 'inferred'."

> "Block 2: the robots that worked on it: 40 welding robots, 6 sealer robots, 10 paint robots."

> "Block 3: 11 torque results, all OK. Block 4: its 9 parts and the supplier lot of each, including door-seal
> lot WS-260904-B."

> "Block 5 is the important one. This car had a cold-weld defect at body inspection. The graph says it was
> caused by anomaly AN-003 on robot RB07 (the same robot from my first example), and the work order that fixed it
> was 4102961. Every line here is one graph query."

### Scene 5 – Ask the plant (3:20–4:20)
**Do:** switch to browser tab 3 (Ask the plant). Click the **Question** box and type:

`Which robot caused the cold welds on 7 and 8 September, and which work order fixed it?`

Press **Enter** and wait about 5 seconds.

**Say:**
> "This is GraphRAG. The language model writes a graph query, my code checks that it's read-only and only uses
> things in the ontology, and then runs it. Every sentence of the answer must cite IDs that are really in the
> result: no citation, no claim."

**Do:** click the **"Cypher (validated, run read-only)"** expander to show the query, then type a second
question:

`Who was the shift supervisor on 9 September?`

**Say:**
> "And if the data doesn't have the answer, it says 'I don't know' instead of guessing. On unseen test
> questions it scored 4 out of 5, and it never invented a fact."

### Scene 6 – Review screen (4:20–4:45) – skip if you're over time
**Do:** switch to browser tab 4 (Review screen). Show the first item with the yellow banner, then click the
**"Backlog (data quality)"** tab.

**Say:**
> "Links the model isn't sure about go to an engineer here. This first one is ranked first because it explains an
> anomaly. Very unlikely links go to a backlog, and for those, a graph-based link prediction suggests the three
> most likely assets. Every decision becomes a new link and a training label."

### Scene 7 – Closing (4:45–5:00)
**Do:** switch back to browser tab 1 (README).

**Say:**
> "To sum up: tag matching F1 1.0, work orders 0.98, with no wrong auto-accepted links; all eight seeded
> anomalies found; and grounded answers that refuse when unsure. The limits are in my report. Thank you."

Press **Stop Recording** in OBS.

---

## Part 4 – Check the video (5 minutes)
1. In OBS: File → **Show Recordings**, open the mp4 and watch all of it.
2. Check these four things:
   - The **text is readable**, even on a phone-size screen.
   - Your **voice is clear** throughout.
   - It's **5:30 or less** (a little over 5:00 is fine; 7 minutes isn't).
   - **No API key and no personal notifications** are visible.
3. If a scene went badly, record again. Two or three takes is normal. Don't edit unless you want to: one clean
   take is best.

## Part 5 – Upload and share (10 minutes)
1. Go to https://studio.youtube.com (sign in with your Google account) → **Create** → **Upload videos** → choose
   the mp4.
2. Title: `Plant DDN-01 – contextualization & knowledge graph (5-min demo)`.
3. "Made for kids": **No**.
4. Visibility: **Unlisted** (only people with the link can watch it, and it won't appear in search) → **Save**.
5. Copy the link (`https://youtu.be/...`).
6. Put it in the README. In GitHub, open README.md → the pencil icon (Edit) → in line 7 replace
   `*link to be added*` with the link → **Commit changes**. Or send the link to me and I'll do it.

Google Drive works too: upload, then right-click → Share → "Anyone with the link" → Viewer → Copy link.

## If something goes wrong while recording
| Problem | Fix |
|---|---|
| `ddn.demo` says it can't connect to Neo4j | Docker Desktop isn't running or Neo4j is still starting: `docker compose up -d`, wait 1 minute |
| `No module named ddn` | You forgot `$env:PYTHONPATH = "src"` in window A |
| The ask screen shows an error or an old answer | Ctrl + C in window B, start it again (see Part 2) |
| The ask screen says "Mode: offline" | Your OpenAI key isn't set in that window: close it, open a new PowerShell, start Streamlit again |
| The answer takes long | Normal: 5–10 seconds per question with an LLM. Keep talking while it loads |
| You make a mistake while talking | Pause 2 seconds and say the sentence again. Short pauses are easy to cut later, or just record again |
