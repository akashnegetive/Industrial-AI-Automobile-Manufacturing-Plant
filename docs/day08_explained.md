# Day 8 – Anomaly detection linked to context (Part E1)

| Piece | Code | Output |
|---|---|---|
| Detectors, context, judgement | `src/ddn/anomaly.py` | `reports/13_anomalies.md`, `data/staging/anomalies.parquet`, `anomaly_vins.parquet` |
| Into the graph | `src/ddn/graph.py` (ontology **v1.2.0**: `exposedTo`) | `AnomalyEvent` nodes; `hasEvent`, `exposedTo`, `causedBy` edges |
| Graph query | `src/ddn/queries.py` (E1) | `reports/12_graph_queries.md` |
| Review priority | `src/ddn/review.py`, `apps/review_app.py` | Anomaly-explaining work orders first |

The one-command run now has **15 steps** (about 7 min). All 63 tests pass; without Neo4j the run gives 13 steps and 59 passed, 4 skipped.

## 1. Result

| ID | Equipment | Window | Verdict | Evidence |
|---|---|---|---|---|
| AN-001 | Press PL1-PR1 | 2 Sep 10:04–16:34 | real, quality | All 28 panel cracks are on cars with panels pressed in the window; WO 4102965 |
| AN-002 | Nutrunner NR14 (TC14) | 3 Sep 08:30 → 4 Sep 10:40 | real, quality | All 38 loose-wheel-nut defects; WO 4102964. Flagged **5½ h before the first NOK** |
| AN-003 | Robot L2-RB07 | 7 Sep 12:45 → 8 Sep 15:14 | real, quality | Small-weld defects at 254× the normal rate; WO 4102961 |
| AN-004 | Sealer SR03 | 9 Sep 06:08–10:24 | real, quality | Roof-ditch leaks at 2,364×; WO 4102962 |
| AN-005 | AHU-TC1 supply fan | 9 → 12 Sep | real, equipment only | No extra defects; WO 4102967 replaced the bearing |
| AN-006 | AHU-TC2 | 10 Sep 13:04–15:34 | real, quality | All 7 craters; WO 4102963 |
| AN-007 | E-coat TT-301 | 11 Sep 00:00–09:29 | **sensor fault** | Flat line while producing; WO 4102968 |
| AN-008 | Oven 2 zone 3 | 12 Sep 02:04–03:34 | **false alarm** | Under 2 h and under +30 °C = inside the bake window (burner manual); 0 extra paint defects |

All 8 signal-visible problems from Part B were found, **with no hand-set limits and no spurious alerts**. The door-seal lot can't be seen in any signal; the genealogy query (D5) finds it.

## 2. The detector, step by step

**Robust rolling z-score.** For each signal:
1. Keep only **production** minutes (no Sundays) and **running** values (above 20% of the signal's typical level). Weld current, flow and tonnage drop to about 0 between cycles; those zeros would make the normal spread huge and hide a drift.
2. **Baseline** = rolling 3-day median, **spread** = rolling 3-day MAD (median absolute deviation). `1.4826 × MAD` equals the standard deviation for normal data, but a few outliers barely move it, unlike a mean and standard deviation.
3. **Lag the baseline** so the current event can't contaminate its own reference:
   - **fast horizon, 12 h lag** for sudden events;
   - **slow horizon, 1 day lag** for gradual degradation. The fan bearing builds over 4 days, and a 12 h baseline would "learn" the drift.
4. `z = (value − baseline) / (1.4826 × MAD)`, smoothed with a 10-minute rolling median.
5. **Hysteresis**, as in industrial alarm systems: an event starts at |z| > 6 and continues while |z| > 3. Gaps under 60 min are merged, and at least 10 minutes must be above 6. Without it, the fan vibration came out as 10 separate alarms.

**Flat-line:** the same value for ≥ 60 min while running means a stuck sensor.

**Torque:** the same z-score on each tool's deviation from its window centre, in 10-minute bins. **A bug found while building it:** the smoothing step asked for 5 points inside a 10-minute window on 10-minute data, which never happens, so every value was empty. The smoothing window must fit the data's resolution.

## 3. Isolation Forest: why it's the comparison, not the alarm
| | Z-score | Isolation Forest |
|---|---|---|
| Known problems | 8/8 | 6, as short fragments |
| Stuck sensor | found | missed (a constant value looks "normal") |
| Unmatched alerts | 0 | 6 |
| Explainable | "9 spreads above its own normal" | "isolated quickly in random trees" |

`contamination = 0.2 %` tells the forest that 0.2% of *every* signal is anomalous, so it always flags something.

## 4. Context: why the graph matters
For each event: **tag → equipment** (approved tag link) → **vehicles exposed**, chosen by what the equipment does:
- touches the car (robot, sealer, nutrunner): the `processedBy` edges in the window;
- conditions a booth (AHU): cars that passed the booth (`feeds` relation `conditions`);
- belongs to a station or line (oven, e-coat): cars that passed it in the window;
- press: the **panel batches pressed in the window**, which are fitted about a day later (genealogy).

Then:
- **defect lift:** the defect code most over-represented on exposed cars compared with all others;
- **confirming work order:** a repair or calibration WO on the equipment from 1 day before to 3 days after, preferring one whose **failure mode fits the anomaly** (low → LOO/PDE, high → HIO/OHE/VIB, flat → AIR). The first version picked a "comm fault" WO for TC14; the rule now picks the calibration WO 4102964.

## 5. Judgement rules (stated per event)
1. Flat line → **sensor_fault**.
2. Exposed cars have a defect at ≥ 5× the normal rate (≥ 3 cases) → **true_positive_quality**.
3. Oven over-temperature under 2 h and under +30 °C → **false_alarm** (MAN-TLN-GM2), even though the deviation was real.
4. No quality impact, but a maintenance WO confirms it → **true_positive_equipment**.
5. Nothing confirms it → **false_alarm**.

## 6. Into the graph (ontology v1.2.0)
- `(:AnomalyEvent)` with window, detector, score, verdict and reason;
- `(equipment)-[:hasEvent]->(event)` and `(sensor)-[:hasEvent]->(event)`;
- `(vehicle)-[:exposedTo {basis}]->(event)`: **2,956** edges (new in v1.2.0);
- `(defect)-[:causedBy]->(event)`: **212** edges, `method=derived`, for events with quality impact only. This is the first place `causedBy` is used, and it's always derived, never a source key.

## 7. Finding: the review queue holds the key work orders
4 of the 8 work orders that explain the incidents (4102961, 4102963, 4102964, 4102967) are still **pending review**. They have long free text and no SAP number, so the matcher gives them medium confidence. The review screen now **shows anomaly-explaining work orders first**, with a banner.

## 8. Honest limitations
- Thresholds 6 / 3 / 10 min and the 20% "running" level are design choices, not tuned to the answers. On real data they'd be set per signal class with operations, and checked against a labelled incident history.
- Each event's window starts where |z| crosses 3. For slow drifts that's later than the physical start: the weld drift is detected from 12:45 on 7 Sep.
- Lift compares exposed cars with all others. When two causes overlap in time (sealer and door-seal lot on 9 Sep), the defect *code* separates them.

## Exercises
- In `anomaly.py`, change `Z_HI` from 6 to 4 and run `python -m ddn.anomaly`. How many extra events appear, and how are they judged?
- Remove the slow horizon (`lag="1D"`) and see which problem disappears.
- In the graph browser: `MATCH (v:Vehicle)-[:exposedTo]->(e:AnomalyEvent {anomaly_id:'AN-004'}) RETURN count(v)`
