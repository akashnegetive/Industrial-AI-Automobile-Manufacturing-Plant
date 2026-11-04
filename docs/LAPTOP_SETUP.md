# Laptop setup (Windows)

Keep this page open: it's updated at the end of every day.

## 1. One-time installs

| What | Needed from | How | Check it works |
|---|---|---|---|
| **Python 3.11+** | Day 1 | python.org installer; tick **"Add python.exe to PATH"** | `python --version` |
| **Git** | Day 1 | git-scm.com, default options | `git --version` |
| **Tesseract OCR** (optional) | Day 6 | UB Mannheim installer: https://github.com/UB-Mannheim/tesseract/wiki, default options | `run_all` step 9 prints `(OCR used)` |
| **Docker Desktop** | Day 7 (Neo4j graph) | docker.com → Docker Desktop for Windows; let it enable **WSL 2**; restart the laptop | `docker run hello-world` |
| **OpenAI API key** (for GraphRAG) | Day 9 | Your key from platform.openai.com → set it as an environment variable (section 6). Never commit it. | `echo $env:OPENAI_API_KEY` shows `sk-...` |
| **Ollama** (local LLM, optional alternative) | Day 9 | ollama.com → Windows installer, then `ollama pull qwen2.5-coder:7b` | `ollama list` |
| Screen recorder | Day 10 (demo video) | Built into Windows: **Win + G** (Xbox Game Bar), or OBS Studio | – |

Docker Desktop is the biggest install (several GB, needs a restart), so do it **before Day 7**.

## 2. One-time project setup

1. `git clone https://github.com/akashnegetive/Industrial-AI-Automobile-Manufacturing-Plant.git`
2. Unzip `Plant_DDN01_Candidate_Pack.zip`, then copy:
   - its `data\` files (14) → `data\raw\`
   - its `documents\` folder → `docs\source_pack\documents\` (7 drawings and 6 manuals inside)

The data and PDFs are deliberately **not** on GitHub. `run_all` stops with a clear message if anything is missing.

## 3. Every day: update and run

In PowerShell, in the project folder:

```powershell
git checkout -- reports docs/ontology.md     # throw away generated files from your last run
git pull                                     # get the day's work
.\run_all.bat                                # or double-click run_all.bat
```

`run_all` installs any new Python libraries by itself when `requirements.txt` changed. That run takes a few extra minutes.

## 4. Expected result, by day

| After day | Steps | Tests | Key lines in the output |
|---|---:|---:|---|
| 5 | 8 | 35 | `Tags ... F1 1.000`, `Work orders ... auto 0.89` |
| 6 | 12 | 48 | `drawings: 145 labels ... (OCR used)` (130 without Tesseract), `passages 316,794 (6,332 inferred)` |
| 7 | 14 | 56 | `graph: 165,698 nodes, 1,133,743 rels ... missing provenance 0`, `7 queries` — **without Docker/Neo4j: 12 steps, 53 passed, 3 skipped** |
| 8 | 15 | 63 | `anomalies: 8 events (true_positive_quality 5, ...)`, `graph: 165,706 nodes, 1,136,926 rels` — **without Docker/Neo4j: 13 steps, 59 passed, 4 skipped** |
| 9 | 16 | 95 | `graph: 165,706 nodes, 1,137,011 rels`, `graphrag (openai): n/10, held-out new n/5, used n/5` (with your key) or `graphrag (offline): 10/10` (no key) — **without Docker/Neo4j: 13 steps, 82 passed, 13 skipped** |
| 10 | 17 | 99 | `predictions_tag_to_asset.csv: 1,541 records, 1,002 not in TRAIN` (new step 9, ddn.export) |

If your numbers differ from this table, or a step fails, paste the last ~30 lines of the output into the chat.

## 5. Day 7 additions: Neo4j and the review screen

**Docker Desktop must be running** (whale icon in the taskbar) before `run_all`. `run_all` starts Neo4j itself
(`docker compose up -d`). The first time, it downloads the Neo4j image (~1 GB); the graph load takes about 4 minutes.

- **Neo4j browser:** http://localhost:7474, user `neo4j`, password `ddn-plant-2026`
- **Review screen:** in PowerShell, in the project folder:
  ```powershell
  .venv\Scripts\streamlit run apps\review_app.py
  ```
  It opens in your browser. Decisions are saved to `data\review\decisions.csv` and used on the next `run_all`.
  Commit and push that file if you want to keep your decisions.
- **Stop Neo4j** when you're done (it uses ~1.5 GB RAM): `docker compose down`. The data is kept for next time.

## 6. Day 9 additions: OpenAI key and the "ask the plant" screen

**Set the key once** (PowerShell; replace the text in quotes with your key, then **close and reopen** PowerShell):

```powershell
setx OPENAI_API_KEY "sk-...your key..."
```

Optional: `setx DDN_LLM_MODEL "gpt-4o-mini"` to use a different model (default `gpt-4o`; mini is cheaper but scored much lower). To force the
no-LLM baseline for one run: `$env:DDN_LLM = "offline"`.

The key lives only in your Windows user environment. It is never written to a file in the project and never
goes to GitHub. Don't paste it into chat, screenshots or the demo video.

- `run_all` step 16 asks the 10 evaluation questions and writes `reports\14_graphrag.md` (the 10 questions cost a
  few cents with gpt-4o).
- Ask your own question from PowerShell:
  ```powershell
  .venv\Scripts\python -m ddn.graphrag ask "Why did water-leak defects rise on Line 2 last Tuesday?"
  ```
  (run `$env:PYTHONPATH = "src"` first in that window.)
- Question screen for the demo: `.venv\Scripts\streamlit run apps\ask_app.py` — shows the answer, its
  citations, the Cypher and the rows.

## 7. Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `git pull` says *local changes would be overwritten* | Reports regenerated by your last run | `git checkout -- reports docs/ontology.md`, then pull |
| `Missing ... data file(s)` / `Found 0/7 drawings` | Pack files not copied | Step 2 above |
| `OCR NOT used` | Tesseract not installed | Install it (table above) |
| `python is not recognized` | Python not on PATH | Reinstall Python with "Add to PATH" ticked |
| Old step/test count after `git pull` | Pull was aborted | Read the `git pull` output; usually the first fix in this table |
| `Neo4j is not reachable - the 2 graph steps will be SKIPPED` | Docker Desktop not running | Start Docker Desktop, wait for "Engine running", run again |
| `docker compose up` fails with a port error | Port 7474/7687 already used (another Neo4j) | Stop the other Neo4j, or `docker compose down` then up |
| Graph load very slow / out of memory | Docker has too little RAM | Docker Desktop → Settings → Resources: give it at least 4 GB |
| `graphrag (offline)` although you set the key | PowerShell window opened before `setx` | Close and reopen PowerShell; check `echo $env:OPENAI_API_KEY` |
| `openai.AuthenticationError` / `401` | Key wrong or revoked | Create a new key, `setx` again, reopen PowerShell |
| `openai.RateLimitError` / `429 insufficient_quota` | No credit on the OpenAI account | Add credit on platform.openai.com, or run offline |
| `model_not_found` | Your account can't use the default model | `setx DDN_LLM_MODEL "gpt-4o-mini"` (or another model you have) |
| Streamlit screen shows an old answer or `AttributeError: ... has no attribute` after `git pull` | The screen was started before the pull and still had the old code in memory | Ctrl + C in its window and start it again (ask_app now reloads GraphRAG by itself) |
