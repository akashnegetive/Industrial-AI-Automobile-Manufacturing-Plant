# Day 6 – Documents, work orders, stations, alarms, VIN traceability (Part C4–C6)

| Step | Code | Report | Staging output |
|---|---|---|---|
| C5 Drawings + manuals (incl. OCR) | `src/ddn/documents.py` | `reports/07_documents.md` | `doc_mentions`, `doc_alarm_codes`, `doc_failure_modes` |
| C4 Work-order failure modes | `src/ddn/workorders.py` | `reports/08_workorders.md` | `wo_failure_modes` |
| Stations, `feeds`, alarms | `src/ddn/context.py` | `reports/09_stations_alarms.md` | `stations`, `feeds`, `alarms` |
| C6 VIN traceability | `src/ddn/trace.py` | `reports/10_vin_traceability.md` | `passages_full`, `processed_by`, `tools`, `part_lots` |

The one-command run (`run_all.bat` / `make all`) now has 12 steps and takes about 50 s. All 48 tests pass, and two runs give identical reports.

## 1. Documents (`documents.py`) – C5

**Drawings**
1. **PyMuPDF** reads the text layer of each page. A page *without* a text layer is a scan, so it's rendered at 300 and 400 dpi and read by **Tesseract OCR** in two layout modes: block mode finds the big labels, sparse mode finds the small ones. The passes are merged.
2. The drawing number gives the **context**: `DWG-BIW-L2-001` means shop BIW, line L2. On the oven-B drawing, "B" means OV2.
3. A table of `LABEL_RULES` turns local labels into asset keys. For example `RB-207` → `RB07`, `TD-2.04` → `ST04TD`, `BNR-B3` → `Z3BR`, `AHU-02` → `AHUTC2`, and the sealer `TE 2(cell)(side)` → that robot's nozzle-temperature tag.
4. Keys resolve through the **same asset index as the tag matcher** (Day 4), so there's one source of truth.
5. Each hit becomes a `mentionedIn` link with page, label, method and confidence.

| How the label was read | Confidence | Band |
|---|---:|---|
| Text layer | 0.95 | auto-accept |
| OCR, exact | 0.85 | review |
| OCR after correction (e.g. `LUB-12` → `LUB-1.2`) | 0.70 | review |

**Results:** 145 labels on the 7 drawings, all resolved. The scan has 18 labels (checked by eye against the image) and OCR recovered **15**. The missing ones are listed in the report, not guessed. OCR corrections are applied only *inside a known label shape*, so ordinary text isn't changed.

**Manuals** link to equipment by **model**, through an explicit table taken from the manual titles. An exact model gets 0.90 (e.g. OR-210 Spot); a model variant gets 0.75 and goes to review (OR-210L). From the manuals, 16 **alarm codes** (message and causes) and 14 **ISO 14224 failure-mode** entries are extracted. Those explain alarms and work orders, and Day 9's question-answering can quote them.

**If Tesseract is missing** (a fresh Windows laptop), the scanned drawing is skipped with a message and everything else still runs. On Windows, install it from the UB Mannheim Tesseract builds and add it to `PATH`.

## 2. Work orders (`workorders.py`) – C4

- **spaCy blank English + EntityRuler** is a rule-based named-entity recognizer. No model download is needed, it works offline, and every extraction can be traced to its rule.
- Entities: `FAILURE` (with the ISO 14224 code as the entity id), `ACTIVITY` (routine work: PM, "within tolerance"), and `EQUIPMENT` (R7, DC tool 14, robot no 13).
- Hinglish is translated first: "trip ho raha hai" → "tripping" → `UST` (spurious stop); "nahi chal raha" → "not running" → `FTS` (fail to start).
- **Results:** 100% of corrective work orders get a failure mode. All 8 root-cause work orders from Day 2 get the right mode: shut height → `PDE`, not heating → `LOO`, valve stuck open → `FTC`, reading frozen → `AIR`, valve hunting → `HIO`.
- **SAP `failure_code` is unrelated to the text.** "Water leak" work orders are coded LEAK only 20% of the time, about the same as chance across 6 codes. So it's never used as a label, and it's now issue #38 in the data-quality report.

## 3. Stations, process flow, alarms (`context.py`)
- **MES station → functional location:** all 46 stations map to an existing asset (`B2-04` → `DDN1-BIW-L2-ST04`, `SLR-2` → `DDN1-PNT-SL-ST02`). Ovens labelled `ASSY` are corrected to `PAINT`.
- **51 `feeds` edges:** the vehicle route in actual order (booth/oven as two parallel paths), each AHU → the booth it conditions, and each press line → the body station where its panels are fitted (from genealogy: PL1 → B2-01, PL2 → B2-05).
- **Alarms:** separators normalised (`BIW/L2/S4/RB07` → `DDN1-BIW-L2-ST04-RB07`). 100% are linked, 231 duplicates are flagged (not deleted), and 59% of events are explained by a manual.

## 4. VIN traceability (`trace.py`) – C6

**Filling missed RFID reads.** Each car's *delay* compared with the typical schedule is interpolated between its own reads. If it was 3 min late at SLR-1 and 5 min late at SLR-3, it was about 4 min late at SLR-2. Filled passages are flagged `inferred=True`.

**Validation.** 2% of *real* reads were hidden and re-estimated: median error 0.28 min, 95.7% within one takt (2.4 min). The errors are large only right after **buffers** (P-INS, T1-01: median ~25 min), where bodies wait for an unpredictable time. So each inferred passage stores its station's 95th-percentile error (`uncertainty_min`), and the confidence of its `processedBy` edges is 0.85 or 0.60 accordingly.

**Booths:** if either the TC or the OV read exists, the pair is known (TC-n → OV-n). For the 3 cars with neither, the booth is marked unknown rather than guessed.

**processedBy:** 511,182 edges. Weld robots, sealer robots, dispensers and paint robots are derived from the station and time. **Nutrunners are observed from the torque results** (the tool channel), not inferred. The robot that moved in Mar-2026 only links to cars after the move.

**Demo trace** (in the report): car `MDDA5XK0XD004375`. Its SLR-2 passage was inferred (reader offline); sealer SR03's nozzle was at **38.3–39.4 °C** while it sealed this car (set point 45); defect: **water leak at the roof ditch**.

## 5. Bugs found today (and why they matter)
| Bug | Effect | Fix |
|---|---|---|
| `TT-301` not recognised | Work order "E-coat TT-301 reading frozen" linked to the ultrafilter UF-301 | ISA-5.1 instrument tags now map to their loop's vessel (`TT-301` → `T301`) |
| pandas 3 stores missing text as `NaN`; `x is not None` is True for NaN | `comp_conflict`, `line_conflict` and `station_conflict` features were wrong for many candidates | `has()` helper; checks rewritten |
| Matcher had no notion of time | "R12 …" before Mar-2026 was linked to L2's robot 12 (it moved there later) | `valid_at_time` feature from the relocation date |
| Threshold ignored error severity | A different-robot error could be auto-accepted | Auto-accept requires zero wrong-machine errors |

After these fixes: work-order F1 is 0.982 and the auto-accept threshold is 0.932, with 0 wrong auto-links.

## Exercises
- Uninstall or rename Tesseract and run `make all`. Check the message and the documents report.
- In `reports/10_vin_traceability.md`, pick the demo car and find its defect, lot and sealer temperature in the raw CSVs by hand. It shows how much work the graph saves.
- Add a phrase to `FAILURE_PHRASES` for something in the "Unclassified" list and re-run `make all`.
