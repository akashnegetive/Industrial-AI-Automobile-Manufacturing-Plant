"""Part B.4 - production problems hidden in the two weeks, with evidence.

Every problem follows the same evidence chain - the same chain the knowledge
graph will answer with one query later:

    signal anomaly window  ->  VINs that passed the equipment in that window
                           ->  defects on those VINs vs. all other VINs
                           ->  confirming work order / alarm / manual text

The "lift" (defect rate inside / defect rate outside) is the key number: a lift
of 1 means no link; a lift of 50 means the window explains the defects.

Run:  python -m ddn.problems     (writes reports/04_production_problems.md)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import REPORTS
from .load import load


@dataclass
class Problem:
    title: str
    equipment: str               # functional location of the cause
    window: str
    signal: str
    exposed: int                 # VINs exposed to the cause
    defect_family: str
    hit_inside: int              # exposed VINs with the defect
    hit_outside: int             # unexposed VINs with the defect
    confirm: list[str] = field(default_factory=list)
    verdict: str = ""

    @property
    def lift(self) -> float:
        total = DATA.n_vins
        inside = self.hit_inside / max(self.exposed, 1)
        outside = self.hit_outside / max(total - self.exposed, 1)
        return inside / outside if outside else float("inf")


class _Data:
    """Load the files once and share them between the problem functions."""
    def __init__(self) -> None:
        self.v = load("vehicles.csv")
        self.p = load("mes_vehicle_passages.csv.gz")
        self.d = load("quality_defects.csv")
        self.g = load("part_lot_genealogy.csv.gz")
        self.tq = load("torque_results.csv.gz")
        self.ts = load("timeseries_1min.csv.gz")
        self.wo = load("maintenance_work_orders.csv")
        self.al = load("alarms_andon_events.csv")
        self.n_vins = len(self.v)


DATA: _Data  # set in main()


def window_of(tag: str, cond, min_gap="15min") -> tuple[pd.Timestamp, pd.Timestamp, pd.Series]:
    """Longest contiguous period where cond(value) is true for a tag."""
    s = DATA.ts[DATA.ts.tag_name == tag].set_index("timestamp").value.sort_index()
    hit = s[cond(s)]
    grp = (hit.index.to_series().diff() > pd.Timedelta(min_gap)).cumsum()
    best = hit.groupby(grp).size().idxmax()
    w = hit[grp == best]
    return w.index.min(), w.index.max(), w


def vins_at(station: str, start, end, infer_from: list[str] | None = None) -> set[str]:
    """VINs read at a station in [start, end]. If the reader missed a car, infer
    its time from the first neighbouring station that did read it, plus the
    median travel time between the two stations (the takt-based fill of Part C6)."""
    p = DATA.p
    at_station = p[p.mes_station == station].set_index("vin").passed_at
    vins = set(at_station[at_station.between(start, end)].index)
    missing = set(DATA.v.vin) - set(at_station.index)
    for nb in infer_from or []:
        nb_time = p[p.mes_station == nb].set_index("vin").passed_at
        offset = (at_station - nb_time).median()          # typical travel time nb -> station
        est = (nb_time + offset).reindex(sorted(missing)).dropna()
        vins |= set(est[est.between(start, end)].index)
        missing -= set(est.index)                         # inferred once, from the nearest neighbour
    return vins


def defect_split(vins: set[str], codes: list[str]) -> tuple[int, int]:
    d = DATA.d[DATA.d.defect_code.isin(codes)]
    inside = d[d.vin.isin(vins)].vin.nunique()
    return inside, d.vin.nunique() - inside


def wo_text(number: str) -> str:
    r = DATA.wo[DATA.wo.wo_number == number].iloc[0]
    return f"WO {number} ({r.created_at:%d %b %H:%M}): {r.short_text}. {r.long_text if pd.notna(r.long_text) else ''}".strip()


# ------------------------------------------------------------------ problems
def press_die_setup() -> Problem:
    s, e, w = window_of("PRS.PL1.PR1.TON", lambda x: x > 1150)
    dc = DATA.al[DATA.al.event_type == "DIE_CHANGE"].iloc[0]
    batches = load("press_panel_batches.csv")
    bad = batches[(batches.press_line == "PL1") & (batches.produced_to > s) & (batches.produced_from < e)]
    vins = set(DATA.g[DATA.g.lot_id.isin(bad.batch_id)].vin)
    i, o = defect_split(vins, ["BP-031"])
    return Problem(
        "Press line 1 die set-up error -> split body-side panels", "DDN1-PRS-PL1-PR1",
        f"{s:%d %b %H:%M} -> {e:%d %b %H:%M}",
        f"PL1 draw-press tonnage up to {w.max():.0f} t (normal ~1050 t, +{w.max() / 1050 - 1:.0%})",
        len(vins), "BP-031 panel split / neck / crack", i, o,
        [f"Alarm {dc.event_id} {dc.event_time:%d %b %H:%M}: {dc.message}",
         f"Batches pressed in window: {', '.join(bad.batch_id)} (consumed ~1 day later at B2-01)",
         wo_text("4102965"),
         "MAN-BPW-1200: tonnage 10-15 % high right after a die change = set-up error -> splits"],
        "Real. Cause: wrong shut height after die change; defects appear a day later because of panel genealogy.")


def nutrunner_offset() -> Problem:
    tq = DATA.tq
    nok = tq[(tq.tool_id == "TC14") & (tq.status == "NOK") & (tq.attempt == 1)]
    rehit = set(zip(tq[tq.attempt == 2].vin, tq[tq.attempt == 2].joint_id))
    escaped = {v for v, j in zip(nok.vin, nok.joint_id) if (v, j) not in rehit}
    i, o = defect_split(escaped, ["AU-077"])
    return Problem(
        "Nutrunner 14 transducer offset -> low wheel-nut torque", "DDN1-ASM-FN1-ST03-NR14",
        f"{nok.timestamp.min():%d %b %H:%M} -> {nok.timestamp.max():%d %b %H:%M}",
        f"TC14 mean wheel torque fell from 120 to ~114 Nm; {len(nok)} NOK first rundowns",
        len(escaped), "AU-077 wheel nut torque low (audit)", i, o,
        [f"{len(nok) - len(escaped)} NOKs re-hit with HW-07; {len(escaped)} NOKs never re-hit",
         wo_text("4102964"),
         "MAN-TQX-DC500 T-11: transducer offset gives systematic low torque"],
        "Real. Safety-relevant: the never-re-hit VINs are the recall scope.")


def weld_current_drift() -> Problem:
    s, e, w = window_of("DDN1_BIW_L2_R07_WELDCUR.PV", lambda x: (x > 3) & (x < 9.5))
    vins = vins_at("B2-04", s, e)
    i, o = defect_split(vins, ["BW-017"])
    return Problem(
        "Robot L2 R07 weld current drift -> cold / undersize welds", "DDN1-BIW-L2-ST04-RB07",
        f"{s:%d %b %H:%M} -> {e:%d %b %H:%M}",
        f"Weld current down to {w.min():.2f} kA (nominal 9.5, robot baseline ~9.96)",
        len(vins), "BW-017 cold weld / undersize / chisel fail", i, o,
        [wo_text("4102961"),
         "MAN-ORN-OR210 E-201: worn caps / failed tip dressing -> low current"],
        "Real. Gradual drift, no hard alarm: a rolling z-score on the robot's own baseline catches it.")


def door_seal_lot() -> Problem:
    # WL-104 = leak at the front door upper edge, i.e. where the door seal sits.
    seals = DATA.g[DATA.g.part_no == "DOOR_SEAL"]
    lot = (DATA.d[DATA.d.defect_code == "WL-104"].merge(seals, on="vin").lot_id.value_counts()
           .reindex(seals.lot_id.unique(), fill_value=0).sort_values(ascending=False))
    bad = lot.index[0]
    rows = seals[seals.lot_id == bad]
    # The lot id was used on 4 Sep and again on 8-10 Sep (lots 0908-0910 never appear).
    # Split its use into sessions separated by a gap of more than 1 day.
    session = (rows.sort_values("fitted_at").fitted_at.diff() > pd.Timedelta("1D")).cumsum()
    rows = rows.sort_values("fitted_at").assign(session=session.values)
    leak_vins = set(DATA.d[DATA.d.defect_code == "WL-104"].vin)
    per = rows.groupby("session").agg(start=("fitted_at", "min"), end=("fitted_at", "max"), n=("vin", "size"),
                                      leaks=("vin", lambda v: len(set(v) & leak_vins)))
    worst = per.leaks.idxmax()
    vins = set(rows[rows.session == worst].vin)
    fitted = rows[rows.session == worst].fitted_at
    i, o = defect_split(vins, ["WL-104"])
    sessions = "; ".join(f"{r.start:%d %b %H:%M}-{r.end:%d %b %H:%M}: {r.n} VINs, {r.leaks} leaks"
                         for r in per.itertuples())
    return Problem(
        f"Supplier door-seal lot {bad} -> water leaks", "Supplier lot (Kumar Weather Seals), fitted at T2-01",
        f"fitted {fitted.min():%d %b %H:%M} -> {fitted.max():%d %b %H:%M}",
        "No sensor signal: found only through part genealogy",
        len(vins), "WL-104 water leak, front door upper (EOL shower test)", i, o,
        [f"WL-104 leaks per lot: {bad} = {lot.iloc[0]}, every other lot <= {lot.iloc[1]}",
         f"Lot id used in separate sessions: {sessions}",
         "Lots WS-260908-* to WS-260910-A never appear: the lot id was probably not updated at T2-01"],
        "Real, but the lot id is not trustworthy: the bad seals are an unrecorded lot fitted 8-10 Sep. "
        "Recall scope = lot id AND fitting time, otherwise 293 good cars from 4 Sep are included.")


def sealer_cold_nozzle() -> Problem:
    s, e, w = window_of("DDN1_PNT_SL_SR03_NOZTEMP.PV", lambda x: (x > 28) & (x < 42))
    margin = pd.Timedelta("5min")   # the nozzle cools/heats gradually; 42 C is our own cut-off
    read = vins_at("SLR-2", s - margin, e + margin)
    vins = vins_at("SLR-2", s - margin, e + margin, infer_from=["SLR-1", "SLR-3", "P-EDO"])
    # WL-101 = roof-ditch leak; DWG-PNT-SL-201 says sealer cell 2 seals the roof ditch.
    i, o = defect_split(vins, ["WL-101"])
    return Problem(
        "Sealer SR03 heater band failure -> roof-ditch water leaks", "DDN1-PNT-SL-ST02-SR03-DSP",
        f"{s:%d %b %H:%M} -> {e:%d %b %H:%M}",
        f"Nozzle temperature down to {w.min():.1f} C (set 45, alarm < 38)",
        len(vins), "WL-101 water leak, roof ditch", i, o,
        [f"RFID reader RD-SLR-2 offline in the same window: only {len(read)} of {len(vins)} VINs were read; "
         "the rest are inferred from the nearest station that read them (SLR-1, else SLR-3, else P-EDO) "
         "plus the median travel time; window padded by 5 min",
         wo_text("4102962"),
         "DWG-PNT-SL-201: cell 2 seals the roof ditch; loss of nozzle heat -> skips and leaks"],
        "Real. Second, independent cause of leaks. It overlaps in time with the seal lot, so the two "
        "are separated by defect location (roof ditch vs door upper), not by date.")


def booth_humidity() -> Problem:
    s, e, w = window_of("PaintShop-AirHandling-AHUTC2-Rh", lambda x: x > 75)
    vins = vins_at("TC-2", s, e)
    i, o = defect_split(vins, ["PD-020"])
    flood = DATA.al[DATA.al.source.str.contains("AHUTC2") & DATA.al.event_time.between(s, e)]
    return Problem(
        "Booth B humidifier valve stuck open -> paint craters", "DDN1-PNT-AHU-AHUTC2-HUM",
        f"{s:%d %b %H:%M} -> {e:%d %b %H:%M}",
        f"Booth B (TC2) RH up to {w.max():.1f} % (spec 65 +/- 5, craters above 75)",
        len(vins), "PD-020 craters (paint inspection)", i, o,
        [f"Alarm flood: {len(flood)} AHUTC2 alarms in the window",
         wo_text("4102963"),
         "MAN-AMX-AHU60K H-15: humidifier valve fails OPEN"],
        "Real. Only booth B cars affected; booth A (TC1) RH normal - good test for the 'feeds' edge.")


def oven_overtemp() -> Problem:
    s, e, w = window_of("PaintShop-OVN2-Z3-Temp", lambda x: x > 320)
    vins = vins_at("OV-2", s, e)
    paint = ["PD-001", "PD-007", "PD-011", "PD-015", "PD-020"]
    i, o = defect_split(vins, paint)
    peak_c = (w.max() - 32) * 5 / 9
    return Problem(
        "Oven 2 zone 3 over-temperature", "DDN1-PNT-OV2-Z3",
        f"{s:%d %b %H:%M} -> {e:%d %b %H:%M}",
        f"Zone 3 up to {w.max():.0f} F = {peak_c:.0f} C (setpoint 150 C, +{peak_c - 150:.0f} C) for "
        f"{(e - s).total_seconds() / 60:.0f} min",
        len(vins), "any paint defect", i, o,
        [wo_text("4102966"),
         "MAN-TLN-GM2: over-temp under 2 h and under +30 C is normally inside the bake window"],
        "Process anomaly, no quality impact: treat as a true alarm but a false *quality* alert.")


def fan_bearing() -> Problem:
    s, e, w = window_of("PaintShop-AHU-AHUTC1SF-Vib", lambda x: x > 4.5, min_gap="60min")
    return Problem(
        "AHU TC1 supply-fan bearing wear (caught before failure)", "DDN1-PNT-AHU-AHUTC1-SF",
        f"{s:%d %b %H:%M} -> {e:%d %b %H:%M}",
        f"Vibration rising from ~2.9 to {w.max():.2f} mm/s (alarm 4.5) over 4 days",
        0, "none", 0, 0,
        [wo_text("4102967"), "After the repair vibration is back to ~2.9 mm/s on 14 Sep"],
        "Real equipment problem with no product impact: a predictive-maintenance example.")


def stuck_sensor() -> Problem:
    return Problem(
        "E-coat bath temperature transmitter TT-301 frozen", "DDN1-PNT-ED-T301",
        "11 Sep 00:00 -> 09:29", "DDN1_PNT_ED_T301_TEMP.PV flat at 31.55 C for 569 min, quality 'Good'",
        0, "none", 0, 0, [wo_text("4102968")],
        "Data problem, not a process problem: the bath was not monitored for 9.5 h. Detect flat-lines.")


PROBLEMS = [press_die_setup, nutrunner_offset, weld_current_drift, door_seal_lot,
            sealer_cold_nozzle, booth_humidity, oven_overtemp, fan_bearing, stuck_sensor]


def to_markdown(probs: list[Problem]) -> str:
    out = ["# Part B.4 – Production problems in 1-14 Sep 2026", "",
           "Generated by `python -m ddn.problems`. Method: anomaly window -> VINs exposed at that equipment "
           "-> their defect rate vs. all other VINs (lift).", "",
           "| # | Problem | Window | Exposed VINs | Defective (exposed / not) | Lift |",
           "|---:|---|---|---:|---|---:|"]
    for n, p in enumerate(probs, 1):
        lift = ("all" if p.hit_outside == 0 else f"{p.lift:.0f}x") if p.exposed else "—"
        hits = f"{p.hit_inside} / {p.hit_outside}" if p.exposed else "—"
        out.append(f"| {n} | {p.title} | {p.window} | {p.exposed or '—'} | {hits} | {lift} |")
    out += [""]
    for n, p in enumerate(probs, 1):
        out += [f"## {n}. {p.title}", "",
                f"- **Equipment:** `{p.equipment}`", f"- **Window:** {p.window}", f"- **Signal:** {p.signal}"]
        if p.exposed:
            out.append(f"- **Defects ({p.defect_family}):** {p.hit_inside} of {p.exposed} exposed VINs "
                       f"vs {p.hit_outside} of {DATA.n_vins - p.exposed} others -> "
                       + ("**every such defect is inside the window**" if p.hit_outside == 0 else f"**lift {p.lift:.0f}x**"))
        out += [f"- **Confirmation:**"] + [f"  - {c}" for c in p.confirm]
        out += [f"- **Verdict:** {p.verdict}", ""]
    return "\n".join(out)


def main() -> None:
    global DATA
    DATA = _Data()
    probs = [f() for f in PROBLEMS]
    path = REPORTS / "04_production_problems.md"
    path.write_text(to_markdown(probs), encoding="utf-8")
    print(f"{len(probs)} problems -> {path}")


if __name__ == "__main__":
    main()
