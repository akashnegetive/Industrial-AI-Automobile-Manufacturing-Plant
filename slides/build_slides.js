// Builds slides/DDN01_interview.pptx (16:9, speaker notes on every slide).
//   npm install pptxgenjs react react-dom react-icons sharp
//   node slides/build_slides.js slides/DDN01_interview.pptx

const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const md = require("react-icons/md");
// applyTheme writes the THEME colours into the deck (from the pptx tooling used to build it); optional.
let applyTheme = async () => {};
try { ({ applyTheme } = require(process.env.APPLY_THEME || "./apply_theme.js")); } catch (e) { console.warn("apply_theme.js not found: theme colours fall back to Office defaults"); }

const OUT = process.argv[2] || "slides.pptx";
const THEME = {
  name: "DDN-01 Plant",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1E252B", lt1: "FFFFFF", dk2: "26343F", lt2: "EEF1F4",
    accent1: "F28C28", accent2: "4A7A96", accent3: "5E9B4C", accent4: "C0392B",
    accent5: "8A99A6", accent6: "B7791F", hlink: "4A7A96", folHlink: "8A99A6",
  },
};
const H = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";               // 10 x 5.625 in
pres.author = "AKASH";
pres.title = "Contextualization and Knowledge Graph for Plant DDN-01";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "TITLE_DARK", background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.45, w: 8.8, h: 1.3, fontSize: 38, bold: true,
      color: C.background1, fontFace: THEME.headFontFace, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 2.9, w: 8.8, h: 1.3, fontSize: 18,
      color: C.background2, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "SECTION_DARK", background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 1.6, w: 8.8, h: 0.6, fontSize: 16, bold: true,
      color: C.accent1, valign: "bottom", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 2.25, w: 8.8, h: 1.1, fontSize: 36, bold: true,
      color: C.background1, fontFace: THEME.headFontFace, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: C.background1 },
  margin: [0.3, 0.5, 0.5, 0.5],
  slideNumber: { x: 9.1, y: 5.22, w: 0.5, h: 0.3, fontSize: 10, color: C.accent5, align: "right" },
  objects: [
    { text: { text: "Plant DDN-01 · contextualization & knowledge graph", options: { x: 0.5, y: 5.22, w: 6, h: 0.3,
      fontSize: 10, color: C.accent5, margin: 0 } } },
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.28, w: 9, h: 0.75, fontSize: 30, bold: true,
      color: C.text2, fontFace: THEME.headFontFace, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
});

// ---------------------------------------------------------------- helpers
async function icon(Comp, color = H.lt1, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + png.toString("base64");
}
async function iconCircle(slide, Comp, x, y, d = 0.5, fill = C.accent1, name = "icon") {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill }, objectName: name + " circle" });
  slide.addImage({ data: await icon(Comp), x: x + d * 0.2, y: y + d * 0.2, w: d * 0.6, h: d * 0.6, altText: name, objectName: name });
}
function num(slide, n, x, y, d = 0.42) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: `step ${n}` });
  slide.addText(String(n), { x, y, w: d, h: d, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true });
}
function card(slide, x, y, w, h, name) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.background2 },
    line: { color: C.background2 }, objectName: name });
}
function bullets(items, size = 14) {
  return items.map((t, i) => {
    const runs = Array.isArray(t) ? t : [{ text: t }];
    return runs.map((r, j) => ({ text: r.text, options: { ...(r.options || {}), fontSize: size, color: (r.options && r.options.color) || C.text1,
      bullet: j === 0 ? { indent: 14 } : undefined, breakLine: j === runs.length - 1 && i < items.length - 1,
      paraSpaceAfter: 5 } }));
  }).flat();
}
const T = (s) => ({ text: s, options: { bold: true } });
function content(title, section) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  return s;
}
function table(slide, rows, opts) {
  const head = rows[0].map((c) => ({ text: c, options: { bold: true, color: C.background1, fill: { color: C.text2 } } }));
  const body = rows.slice(1).map((r) => r.map((c) => (typeof c === "object" ? c : { text: String(c) })));
  slide.addTable([head, ...body], { fontSize: 12, color: C.text1, border: { type: "solid", pt: 0.5, color: H.lt2 },
    fill: { color: C.background1 }, margin: [2, 5, 2, 5], valign: "middle", ...opts });
}
const verdictColor = { true_positive_quality: C.accent4, true_positive_equipment: C.accent2, sensor_fault: C.accent6, false_alarm: C.accent3 };

(async () => {
  // ============================================================ 1 title
  pres.addSection({ title: "Opening" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Opening" });
  s.addText("Contextualizing Plant DDN-01", { placeholder: "title" });
  s.addText([
    { text: "From siloed plant records to a trustworthy knowledge graph", options: { breakLine: true } },
    { text: "Industrial AI take-home · AKASH · November 2026", options: { fontSize: 14, color: C.accent1 } },
  ], { placeholder: "body" });
  s.addNotes("Introduce yourself in one sentence. Then: 'I built a working pipeline that links the plant's siloed records to one asset hierarchy, loads them into a Neo4j knowledge graph with provenance on every edge, and uses that graph for anomaly detection and grounded question answering. Everything runs with one command on the synthetic DDN-01 pack. I'll show results, design choices and the limits, then walk through the code.'");

  // ============================================================ agenda
  s = content("Plan for the 45 minutes", "Opening");
  const agenda = [
    ["0–5", "Problem and results", "one robot, five names · what I built · four numbers"],
    ["5–8", "Part A", "how Cognite, Siemens and AWS do it; what I borrowed"],
    ["8–11", "Part B", "data quality and the nine production problems"],
    ["11–19", "Part C", "matching, thresholds, review loop, one work order end to end"],
    ["19–24", "Part D", "ontology, provenance, queries, one VIN end to end"],
    ["24–29", "Part E", "anomalies in context, GraphRAG and how it was evaluated"],
    ["29–32", "Limits and scale", "what I'd say before you ask"],
    ["32–45", "Live demo, code, questions", "run it, open the code, your questions"],
  ];
  agenda.forEach((a, i) => {
    const y = 1.15 + i * 0.49;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5, y, w: 1.0, h: 0.4, rectRadius: 0.06, fill: { color: i === 7 ? C.accent1 : C.background2 },
      line: { color: i === 7 ? C.accent1 : C.background2 }, objectName: `agenda time ${i + 1}` });
    s.addText(a[0] + " min", { x: 0.5, y, w: 1.0, h: 0.4, fontSize: 13, bold: true, color: i === 7 ? C.background1 : C.text2, align: "center", valign: "middle", margin: 0, isTextBox: true });
    s.addText([{ text: a[1] + "  ", options: { bold: true, color: C.text2 } }, { text: a[2], options: { color: C.text1 } }],
      { x: 1.7, y, w: 7.8, h: 0.4, fontSize: 14, valign: "middle", margin: 0, isTextBox: true });
  });
  s.addNotes("Say the plan in one sentence and keep to it: about 30 minutes of slides, then live demo and code. If they interrupt with questions, use the backup slides at the end.");

  // ============================================================ 2 problem
  s = content("One robot, five names", "Opening");
  table(s, [
    ["System", "Record for the same welding robot"],
    ["SAP PM", "DDN1-BIW-L2-ST04-RB07 (equipment 10007731)"],
    ["PI historian", "DDN1_BIW_L2_R07_WELDCUR.PV"],
    ["Work order", "\"R7 gun tip dressing fail, cap changed\""],
    ["Cell drawing", "RB-207"],
    ["MES / RFID", "Station B2-04, reader RD-B2-04"],
  ], { x: 0.5, y: 1.25, w: 5.6, colW: [1.5, 4.1], fontSize: 14, rowH: 0.58 });
  card(s, 6.45, 1.25, 3.05, 3.6, "callout card");
  await iconCircle(s, md.MdLinkOff, 6.7, 1.45, 0.55, C.accent1, "no shared key icon");
  s.addText([
    { text: "No shared key", options: { bold: true, fontSize: 16, breakLine: true } },
    { text: "Every system names equipment its own way, with typos, legacy names and Hinglish shorthand.", options: { fontSize: 14, breakLine: true } },
    { text: " ", options: { fontSize: 8, breakLine: true } },
    { text: "Defects never name a machine", options: { bold: true, fontSize: 16, breakLine: true } },
    { text: "Only VIN → station → time → equipment connects a defect to its cause.", options: { fontSize: 14 } },
  ], { x: 6.7, y: 2.1, w: 2.6, h: 2.6, color: C.text1, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("The core problem: one physical robot has five identities. Point at R07 vs RB07, and the drawing's RB-207 which means line 2 robot 07. Defects are logged against VIN and inspection point only, so without contextualization you cannot ask 'which machine caused this'.");

  // ============================================================ 3 what I built
  s = content("What I built", "Opening");
  const steps = [
    [md.MdInput, "Ingest", "pydantic staging, tag parsing, °F→°C"],
    [md.MdFilterAlt, "Block", "TF-IDF top-15 + token index"],
    [md.MdRule, "Score", "rules + LightGBM on 20 features"],
    [md.MdFactCheck, "Gate", "auto-accept / engineer review"],
    [md.MdHub, "Graph", "Neo4j + provenance; values in Parquet"],
    [md.MdAutoAwesome, "AI", "anomaly events + GraphRAG"],
  ];
  for (let i = 0; i < steps.length; i++) {
    const x = 0.5 + i * 1.53;
    card(s, x, 1.35, 1.38, 2.25, `step card ${i + 1}`);
    await iconCircle(s, steps[i][0], x + 0.42, 1.55, 0.55, C.accent1, `${steps[i][1]} icon`);
    s.addText(steps[i][1], { x: x + 0.08, y: 2.2, w: 1.22, h: 0.4, fontSize: 16, bold: true, color: C.text2, align: "center", margin: 0, isTextBox: true });
    s.addText(steps[i][2], { x: x + 0.08, y: 2.6, w: 1.22, h: 0.95, fontSize: 13, color: C.text1, align: "center", valign: "top", margin: 0, isTextBox: true });
    if (i < steps.length - 1) s.addShape(pres.shapes.LINE, { x: x + 1.39, y: 1.82, w: 0.13, h: 0, line: { color: C.accent5, width: 1.5, endArrowType: "triangle" }, objectName: `arrow ${i + 1}` });
  }
  s.addText([
    { text: "One command: ", options: { bold: true } },
    { text: "run_all.bat (Windows) or make all  ·  17 steps  ·  99 tests  ·  synthetic DDN-01 pack only" },
  ], { x: 0.5, y: 4.05, w: 9, h: 0.5, fontSize: 14, color: C.text2, margin: 0, isTextBox: true });
  s.addText("Thresholds, review band and backlog follow the assignment's Figure 1; thresholds come from the precision–recall curve, not from the example values.",
    { x: 0.5, y: 4.5, w: 9, h: 0.5, fontSize: 12, italic: true, color: C.accent5, margin: 0, isTextBox: true });
  s.addNotes("Walk left to right. Stress two design rules: only confident or engineer-approved links enter the graph, and every edge carries provenance so anyone can ask 'why does the graph think this?'.");

  // ============================================================ 4 results
  s = content("Results at a glance", "Opening");
  const stats = [
    ["1.000 / 0.982", "entity-matching F1", "tags / work orders, out-of-fold"],
    ["0", "wrong auto-accepted links", "precision 1.000 in the auto band"],
    ["8 / 8", "signal problems found", "1 judged a false alarm, with reasons"],
    ["4 / 5", "unseen GraphRAG questions", "manually reviewed; never an invented fact"],
  ];
  stats.forEach((st, i) => {
    const x = 0.5 + (i % 2) * 4.6, y = 1.3 + Math.floor(i / 2) * 1.75;
    card(s, x, y, 4.4, 1.55, `stat card ${i + 1}`);
    s.addText(st[0], { x: x + 0.25, y: y + 0.12, w: 3.9, h: 0.75, fontSize: 40, bold: true, color: C.accent1, fontFace: THEME.headFontFace, margin: 0, isTextBox: true });
    s.addText([{ text: st[1], options: { bold: true, breakLine: true } }, { text: st[2], options: { color: C.accent5 } }],
      { x: x + 0.25, y: y + 0.88, w: 3.9, h: 0.6, fontSize: 14, color: C.text1, margin: 0, isTextBox: true });
  });
  s.addText("Matching scores are out-of-fold on the TRAIN labels; the evaluator's hidden test set is the real measure (predictions in outputs/).",
    { x: 0.5, y: 4.85, w: 9, h: 0.3, fontSize: 11, italic: true, color: C.accent5, margin: 0, isTextBox: true });
  s.addNotes("Give the four numbers, then immediately the caveat: TRAIN out-of-fold, so hidden test is the real measure. Being honest about this early builds trust.");

  // ============================================================ Part A
  pres.addSection({ title: "Part A – Research" });
  s = pres.addSlide({ masterName: "SECTION_DARK", sectionTitle: "Part A – Research" });
  s.addText("PART A", { placeholder: "body" });
  s.addText("How industrial platforms contextualize", { placeholder: "title" });

  s = content("Three platforms, one pattern", "Part A – Research");
  const vendors = [
    ["Cognite Data Fusion", ["Containers (storage) vs views (how roles see data)", "Rules + supervised entity matching, score threshold", "Annotations: confidence + suggested / approved / rejected"]],
    ["Siemens", ["Insights Hub asset types from variables + aspects", "IIH Semantics: GraphQL over a knowledge graph", "Industrial Copilot: code and fault diagnosis"]],
    ["AWS IoT TwinMaker", ["Entities + components; relations become graph edges", "PartiQL MATCH with variable-length paths", "Values stay in SiteWise / Timestream"]],
  ];
  vendors.forEach((v, i) => {
    const x = 0.5 + i * 3.05;
    card(s, x, 1.25, 2.9, 2.65, `vendor card ${v[0]}`);
    s.addText(v[0], { x: x + 0.2, y: 1.37, w: 2.5, h: 0.45, fontSize: 16, bold: true, color: C.text2, margin: 0, isTextBox: true });
    s.addText(bullets(v[1], 13), { x: x + 0.15, y: 1.85, w: 2.6, h: 1.95, valign: "top", margin: 0, isTextBox: true });
  });
  await iconCircle(s, md.MdLightbulb, 0.5, 4.1, 0.5, C.accent1, "borrowed ideas icon");
  s.addText([
    { text: "Borrowed: ", options: { bold: true } },
    { text: "rules and confirmed matches before ML · confidence + status on every link · decisions reused as labels · container/view split · values outside the graph" },
  ], { x: 1.15, y: 4.05, w: 8.35, h: 0.65, fontSize: 14, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
  s.addText("Every claim is cited to vendor documentation in docs/part_a_research.md.", { x: 0.5, y: 4.8, w: 9, h: 0.3, fontSize: 11, italic: true, color: C.accent5, margin: 0, isTextBox: true });
  s.addNotes("Cognite is the most explicit about predicted links and confidence; Siemens and AWS mostly configure links rather than predict them. Say which idea you borrowed for which part. Admit gaps: no named Cognite automotive case found; AAS support in Siemens is a separate product (assetfox).");

  // ============================================================ Part B
  pres.addSection({ title: "Part B – Data" });
  s = pres.addSlide({ masterName: "SECTION_DARK", sectionTitle: "Part B – Data" });
  s.addText("PART B", { placeholder: "body" });
  s.addText("Understanding the data pack", { placeholder: "title" });

  s = content("38 data-quality issues, 15 not documented", "Part B – Data");
  const ds = ["work orders", "tags", "assets", "time series", "alarms", "torque", "defects", "MES passages", "other (4 files)"];
  const doc = [5, 5, 3, 3, 3, 1, 1, 2, 0], neu = [2, 1, 2, 2, 1, 2, 2, 0, 3];
  s.addChart(pres.charts.BAR, [
    { name: "in data dictionary", labels: ds, values: doc },
    { name: "new (found by profiling)", labels: ds, values: neu },
  ], { x: 0.4, y: 1.15, w: 5.4, h: 3.85, barDir: "bar", barGrouping: "stacked", chartColors: [H.accent5, H.accent1],
    catAxisLabelColor: H.dk1, valAxisLabelColor: H.accent5, catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", valGridLine: { color: H.lt2, size: 0.5 }, catGridLine: { style: "none" },
    catAxisOrientation: "maxMin", showLegend: true, legendPos: "b", legendFontSize: 11, legendFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "ctr", dataLabelColor: H.lt1, dataLabelFontSize: 10, dataLabelFontFace: "+mn-lt",
    showTitle: true, title: "Issues per dataset", titleFontSize: 13, titleColor: H.dk2, titleFontFace: "+mn-lt" });
  s.addText(bullets([
    [T("Relocated robot "), { text: "keeps its old tag name" }],
    [T("°F and °C "), { text: "in one historian" }],
    [T("Stuck sensor "), { text: "and a 3 h outage" }],
    [T("815 alarms "), { text: "write S3 for ST03" }],
    [T("SAP failure codes "), { text: "contradict the WO text" }],
    [T("Lot id reused "), { text: "across two fitting sessions" }],
  ], 14), { x: 6.1, y: 1.3, w: 3.4, h: 3.6, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("Every issue has a count and examples you can verify (reports/02). The ones not in the dictionary are the interesting ones: relocated robot, S3 vs ST03, lot id reuse. These later explain matcher errors and the recall scope.");

  s = content("Nine real production problems", "Part B – Data");
  table(s, [
    ["#", "Problem", "Exposed VINs", "Defective exposed / not", "Lift"],
    ["1", "Press line 1 die set-up → split panels", "300", "28 / 0", "all"],
    ["2", "Nutrunner NR14 offset → low wheel-nut torque", "37", "37 / 0", "all"],
    ["3", "Robot L2 R07 weld-current drift → cold welds", "634", "101 / 6", "174×"],
    ["4", "Door-seal lot WS-260904-B → water leaks", "1,492", "85 / 0", "all"],
    ["5", "Sealer SR03 heater failure → roof-ditch leaks", "106", "36 / 1", "2,409×"],
    ["6", "Booth B humidifier stuck open → craters", "29", "7 / 0", "all"],
    ["7", "Oven 2 zone 3 over-temperature", "19", "0 / 81", "false alarm"],
    ["8", "AHU TC1 fan bearing wear", "–", "–", "caught early"],
    ["9", "E-coat TT-301 transmitter frozen", "–", "–", "sensor fault"],
  ], { x: 0.5, y: 1.2, w: 9, colW: [0.4, 4.6, 1.2, 1.7, 1.1], fontSize: 12, rowH: 0.37 });
  s.addNotes("Method: anomaly window → VINs exposed at that equipment → defect rate vs all other VINs. Highlight #4: the lot id was reused, so recall by lot id alone includes 293 good cars. #7 is the deliberate false alarm.");

  // ============================================================ Part C
  pres.addSection({ title: "Part C – Pipeline" });
  s = pres.addSlide({ masterName: "SECTION_DARK", sectionTitle: "Part C – Pipeline" });
  s.addText("PART C", { placeholder: "body" });
  s.addText("Contextualization pipeline", { placeholder: "title" });

  s = content("Match: block, score, gate", "Part C – Pipeline");
  const cs = [
    ["Block", "375 → ~25 candidates per record", "blocking recall 1.000 tags · 0.999 work orders"],
    ["Features", "20 per pair", "rule agreement, fuzzy name/FL, line & component conflicts, unit fits type, valid at the record's time"],
    ["Model", "LightGBM", "GroupKFold out-of-fold: no record scored by a model that saw its label"],
    ["Gate", "threshold from the PR curve", "precision ≥ 0.995 and no wrong-machine error in the auto band"],
  ];
  cs.forEach((c, i) => {
    const y = 1.2 + i * 0.95;
    num(s, i + 1, 0.5, y + 0.1);
    s.addText([{ text: c[0] + "  ", options: { bold: true, color: C.text2 } }, { text: c[1], options: { color: C.accent1, bold: true } }],
      { x: 1.1, y, w: 8.4, h: 0.4, fontSize: 16, margin: 0, isTextBox: true });
    s.addText(c[2], { x: 1.1, y: y + 0.4, w: 8.4, h: 0.45, fontSize: 14, color: C.text1, margin: 0, isTextBox: true });
  });
  s.addNotes("Blocking matters because a true asset missing from the candidates can never be recovered; that's why I report blocking recall. Out-of-fold scoring avoids grading the model on records it trained on. The threshold is chosen by the cost of a wrong link, not by maximising F1.");

  s = content("Rules vs ML: where each fails", "Part C – Pipeline");
  s.addChart(pres.charts.BAR, [
    { name: "rules only", labels: ["Tags", "Work orders"], values: [0.987, 0.95] },
    { name: "ML", labels: ["Tags", "Work orders"], values: [1.0, 0.982] },
  ], { x: 0.4, y: 1.15, w: 4.6, h: 3.85, barDir: "col", barGrouping: "clustered", chartColors: [H.accent5, H.accent1],
    valAxisMinVal: 0.9, valAxisMaxVal: 1.0, valAxisLabelFormatCode: "0.00", catAxisLabelColor: H.dk1, valAxisLabelColor: H.accent5,
    catAxisLabelFontSize: 12, valAxisLabelFontSize: 10, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    valGridLine: { color: H.lt2, size: 0.5 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "b", legendFontSize: 11, legendFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.000", dataLabelColor: H.dk1, dataLabelFontSize: 11, dataLabelFontFace: "+mn-lt",
    showTitle: true, title: "F1, out-of-fold on TRAIN", titleFontSize: 13, titleColor: H.dk2, titleFontFace: "+mn-lt" });
  s.addText([
    { text: "Rules fail on noise", options: { bold: true, color: C.text2, fontSize: 16, breakLine: true } },
    { text: "DD1_ for DDN1_, glued sub-units (PR2LUB), Hinglish with no code", options: { fontSize: 14, breakLine: true } },
    { text: " ", options: { fontSize: 8, breakLine: true } },
    { text: "ML fails on ambiguity", options: { bold: true, color: C.text2, fontSize: 16, breakLine: true } },
    { text: "\"RB01 gun water leak\" without a line; robot vs its weld gun", options: { fontSize: 14, breakLine: true } },
    { text: " ", options: { fontSize: 8, breakLine: true } },
    { text: "ML fixed 14 tags + 51 work orders the rules missed and broke none", options: { fontSize: 14, bold: true, color: C.accent1 } },
  ], { x: 5.3, y: 1.3, w: 4.2, h: 3.6, color: C.text1, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("Rules are kept as a baseline AND as a feature. The remaining ML errors are genuinely ambiguous records, which is exactly what the review band is for.");

  s = content("Threshold set by the cost of a wrong link", "Part C – Pipeline");
  s.addChart(pres.charts.BAR, [{ name: "wrong auto-links", labels: ["0.50", "0.70", "0.80", "0.90", "0.932", "0.95"], values: [4, 3, 2, 1, 0, 0] }],
    { x: 0.4, y: 1.15, w: 4.8, h: 3.85, barDir: "col", chartColors: [H.accent4, H.accent4, H.accent4, H.accent4, H.accent3, H.accent3],
      catAxisLabelColor: H.dk1, valAxisLabelColor: H.accent5, catAxisLabelFontSize: 11, valAxisLabelFontSize: 10, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
      valGridLine: { color: H.lt2, size: 0.5 }, catGridLine: { style: "none" }, showLegend: false, valAxisMaxVal: 5,
      showValue: true, dataLabelPosition: "outEnd", dataLabelColor: H.dk1, dataLabelFontSize: 11, dataLabelFontFace: "+mn-lt",
      showTitle: true, title: "Work orders: wrong auto-links per threshold", titleFontSize: 13, titleColor: H.dk2, titleFontFace: "+mn-lt",
      showCatAxisTitle: true, catAxisTitle: "auto-accept threshold (0.932 chosen)", catAxisTitleFontSize: 11, catAxisTitleColor: H.accent5, catAxisTitleFontFace: "+mn-lt" });
  s.addText(bullets([
    [T("Why: "), { text: "a wrong link sends a recall investigation to the wrong machine" }],
    [T("Auto band: "), { text: "95.7% of WOs linked with 0 errors" }],
    [T("Review queue: "), { text: "9 tags, 122 WOs, 44 document mentions" }],
    [T("Engineer decisions "), { text: "become method=engineer edges and new training labels" }],
  ], 14), { x: 5.5, y: 1.3, w: 4.0, h: 3.6, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("Interview Q3: how did you set the threshold? Lowest score where out-of-fold precision ≥ 0.995 and no wrong-machine error. A wrong auto-accepted link costs far more than a link waiting for review. Work orders that explain an anomaly are shown first in the review screen.");

  s = content("One work order, raw text to graph edge", "Part C – Pipeline");
  card(s, 0.5, 1.2, 9, 0.85, "raw text card");
  s.addText([
    { text: "WO 4102961  ", options: { bold: true, color: C.accent1 } },
    { text: "\"R7 gun tip dressing fail, cap changed\" · \"Weld current low aa raha tha since yesterday. L2 ST4 robot 7. Tip dresser blade chipped…\"", options: { italic: true } },
  ], { x: 0.7, y: 1.25, w: 8.6, h: 0.75, fontSize: 13, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
  const wf = [
    ["Normalise", "Hinglish → \"current low\"; ST4 → ST04; R7 / robot 7 → RB07"],
    ["Extract", "tokens L2 · ST04 · RB07 + components WG, TD; ISO 14224 LOO (low output)"],
    ["Match", "top candidate RB07-WG (weld gun) at a low score → review band"],
    ["Review", "ranked first: explains anomaly AN-003; engineer approves or corrects"],
    ["Edge", "method=engineer, confidence 1.0, reused as a training label"],
  ];
  wf.forEach((w, i) => {
    const y = 2.25 + i * 0.52;
    num(s, i + 1, 0.5, y + 0.03, 0.38);
    s.addText([{ text: w[0] + ": ", options: { bold: true, color: C.text2 } }, { text: w[1] }],
      { x: 1.05, y, w: 8.45, h: 0.45, fontSize: 14, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
  });
  s.addNotes("Interview Q1. Where it can go wrong: the text names the robot, its gun AND the tip dresser; SAP could hold the order on any of the three. That is why it is not auto-accepted. Other risks: wrong line when the line is missing, misread Hinglish, SAP failure codes that contradict the text.");

  // ============================================================ Part D
  pres.addSection({ title: "Part D – Graph" });
  s = pres.addSlide({ masterName: "SECTION_DARK", sectionTitle: "Part D – Graph" });
  s.addText("PART D", { placeholder: "body" });
  s.addText("Building and querying the knowledge graph", { placeholder: "title" });

  s = content("Ontology first, provenance on every edge", "Part D – Graph");
  const gs = [["18 / 19", "node / edge types (YAML v1.3)"], ["165,706", "nodes"], ["1.14 M", "relationships"], ["0", "edges without provenance"]];
  gs.forEach((g, i) => {
    const y = 1.2 + i * 0.93;
    s.addText(g[0], { x: 0.5, y, w: 2.1, h: 0.55, fontSize: 28, bold: true, color: C.accent1, fontFace: THEME.headFontFace, margin: 0, isTextBox: true });
    s.addText(g[1], { x: 0.5, y: y + 0.52, w: 2.6, h: 0.35, fontSize: 13, color: C.text1, margin: 0, isTextBox: true });
  });
  card(s, 3.3, 1.2, 6.2, 1.6, "edge example card");
  s.addText([
    { text: "(RB07)-[:hasTimeSeries]->(TimeSeries)", options: { bold: true, fontFace: "Courier New", fontSize: 13, color: C.text2, breakLine: true } },
    { text: "source_system PIPELINE · method rule · confidence 1.0 · status approved · created_at · evidence \"rules (exact) and ML agree\"", options: { fontSize: 13 } },
  ], { x: 3.5, y: 1.3, w: 5.8, h: 1.4, color: C.text1, valign: "top", margin: 0, isTextBox: true });
  s.addText(bullets([
    [T("Property graph (Neo4j): "), { text: "path questions with properties on edges; maps onto Cognite DMS" }],
    [T("Time-valid partOf: "), { text: "robot RB12 moved L1 → L2; old VINs keep the old line" }],
    [T("Values in Parquet: "), { text: "graph holds a store_uri pointer" }],
  ], 14), { x: 3.3, y: 3.0, w: 6.2, h: 2.0, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("Interview Q2 and Q5. RDF would win for cross-company semantic integration (AAS, suppliers); property graph wins for edge properties like time and confidence. Relocation: partOf has valid_from/valid_to, queries filter by the VIN's time. Containers vs views: one storage schema, three role views (maintenance, quality, traceability) in the ontology file.");

  s = content("Queries that answer plant questions", "Part D – Graph");
  const qs = [
    [md.MdBuild, "D3 · Calibration gap", "NR14 had no calibration work order in 12 months, one of only 2 of 20 nutrunners. It is the one that drifted."],
    [md.MdLocalShipping, "D5 · Recall scope", "Lot id gives 1,785 vehicles; fitting time narrows it to 1,492, sparing 293 good cars."],
    [md.MdInsights, "D7 · Plant head", "1,492 + 647 + 106 + 37 cars carried a known risk; inspection caught only part of them."],
  ];
  for (let i = 0; i < qs.length; i++) {
    const x = 0.5 + i * 3.05;
    card(s, x, 1.25, 2.9, 2.9, `query card ${i + 1}`);
    await iconCircle(s, qs[i][0], x + 0.2, 1.45, 0.55, C.accent1, `${qs[i][1]} icon`);
    s.addText(qs[i][1], { x: x + 0.2, y: 2.12, w: 2.5, h: 0.45, fontSize: 16, bold: true, color: C.text2, margin: 0, isTextBox: true });
    s.addText(qs[i][2], { x: x + 0.2, y: 2.6, w: 2.5, h: 1.9, fontSize: 14, color: C.text1, valign: "top", margin: 0, isTextBox: true });
  }
  s.addText("All seven required queries, with Cypher and real output: reports/12_graph_queries.md and the report's Appendix A.",
    { x: 0.5, y: 4.35, w: 9, h: 0.35, fontSize: 11, italic: true, color: C.accent5, margin: 0, isTextBox: true });
  s.addNotes("Pick these three because they are decisions a plant would actually take: calibration plan, recall scope, inspection effectiveness. Offer to run any query live in the Neo4j browser.");

  s = content("One VIN, end to end", "Part D – Graph");
  const tl = [["08:55", "body start", "BIW line 1"], ["40", "weld robots", "processedBy"], ["6 + 10", "sealer + paint", "robots"], ["11", "torque joints", "all OK"], ["9", "parts + lots", "incl. WS-260904-B"], ["20:00", "EOL audit", "44 stations"]];
  s.addShape(pres.shapes.LINE, { x: 0.8, y: 1.75, w: 8.4, h: 0, line: { color: C.accent5, width: 2 }, objectName: "timeline" });
  tl.forEach((t, i) => {
    const x = 0.5 + i * 1.6;
    s.addShape(pres.shapes.OVAL, { x: x + 0.45, y: 1.6, w: 0.3, h: 0.3, fill: { color: C.accent1 }, line: { color: C.background1, width: 2 }, objectName: `timeline point ${i + 1}` });
    s.addText([{ text: t[0], options: { bold: true, fontSize: 18, color: C.text2, breakLine: true } }, { text: t[1], options: { fontSize: 13, breakLine: true } }, { text: t[2], options: { fontSize: 11, color: C.accent5 } }],
      { x, y: 2.0, w: 1.2, h: 1.1, align: "center", color: C.text1, valign: "top", margin: 0, isTextBox: true });
  });
  s.addText("MDDA5XK00D003924 · Hatch 1.2 MT · 8 Sep 2026", { x: 0.5, y: 1.1, w: 9, h: 0.35, fontSize: 14, bold: true, color: C.accent1, margin: 0, isTextBox: true });
  card(s, 0.5, 3.35, 9, 1.4, "defect chain card");
  await iconCircle(s, md.MdReportProblem, 0.7, 3.6, 0.55, C.accent4, "defect icon");
  s.addText([
    { text: "D700356 BW-017 weld nugget small", options: { bold: true, breakLine: true } },
    { text: "causedBy AN-003 on robot DDN1-BIW-L2-ST04-RB07 (derived, confidence 0.9) → fixed by WO 4102961. Every line is one Cypher query result." },
  ], { x: 1.45, y: 3.45, w: 7.9, h: 1.2, fontSize: 14, color: C.text1, valign: "middle", margin: 0, isTextBox: true });
  s.addNotes("This is the demo video's second story (python -m ddn.demo vin). Mention inferred passages: missed RFID reads are filled from takt time and flagged; validated by hiding 5,793 real reads, median error 0.28 min.");

  // ============================================================ Part E
  pres.addSection({ title: "Part E – AI" });
  s = pres.addSlide({ masterName: "SECTION_DARK", sectionTitle: "Part E – AI" });
  s.addText("PART E", { placeholder: "body" });
  s.addText("AI on top of the graph", { placeholder: "title" });

  s = content("8 anomalies, judged in context", "Part E – AI");
  const an = [
    ["AN-001", "Press PL1-PR1 tonnage", "true_positive_quality"], ["AN-002", "Nutrunner NR14 torque", "true_positive_quality"],
    ["AN-003", "Robot L2 RB07 weld current", "true_positive_quality"], ["AN-004", "Sealer SR03 nozzle temp", "true_positive_quality"],
    ["AN-005", "AHU TC1 fan vibration", "true_positive_equipment"], ["AN-006", "AHU TC2 humidity", "true_positive_quality"],
    ["AN-007", "E-coat TT-301 flat line", "sensor_fault"], ["AN-008", "Oven 2 zone 3 over-temp", "false_alarm"],
  ];
  table(s, [["Event", "Signal", "Verdict"], ...an.map((a) => [a[0], a[1], { text: a[2].replace(/_/g, " "), options: { bold: true, color: verdictColor[a[2]] } }])],
    { x: 0.5, y: 1.2, w: 5.6, colW: [1.0, 2.6, 2.0], fontSize: 12, rowH: 0.4 });
  s.addText(bullets([
    [T("Robust z-score "), { text: "against each signal's own lagged 3-day median/MAD, while producing" }],
    [T("Written to the graph "), { text: "on equipment + tag, exposedTo VINs" }],
    [T("Judged "), { text: "by defect lift, a confirming WO and the manual's bake window" }],
    [T("Isolation Forest "), { text: "as comparison only: more windows, less meaning" }],
  ], 14), { x: 6.4, y: 1.25, w: 3.1, h: 3.7, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("AN-008 is the false alarm: the over-temperature was real but under 2 h and under +30 °C, inside the bake window in the oven manual, and the cars in the oven had no extra defects. AN-007 is a data problem, not a process problem.");

  s = content("GraphRAG: grounded or silent", "Part E – AI");
  const rag = [["Question", md.MdQuestionAnswer], ["LLM writes Cypher", md.MdCode], ["Validate", md.MdVerifiedUser], ["Read-only run", md.MdLock], ["Cited answer", md.MdFormatQuote]];
  for (let i = 0; i < rag.length; i++) {
    const x = 0.5 + i * 1.85;
    await iconCircle(s, rag[i][1], x + 0.5, 1.2, 0.6, C.accent1, `${rag[i][0]} icon`);
    s.addText(rag[i][0], { x, y: 1.88, w: 1.6, h: 0.4, fontSize: 14, bold: true, color: C.text2, align: "center", margin: 0, isTextBox: true });
  }
  s.addText(bullets([
    [T("Validator: "), { text: "no write keywords; labels, relationships, properties and arrow directions checked against the ontology; EXPLAIN; LIMIT" }],
    [T("No citation, no claim: "), { text: "every cited ID must appear in the result rows, or the sentence is dropped" }],
    [T("Three ways to \"I don't know\": "), { text: "schema can't answer · 0 rows · nothing survives grounding" }],
    [T("LLM: "), { text: "OpenAI gpt-4o, temperature 0, structured JSON; Claude, Ollama and an offline mode are switchable" }],
  ], 14), { x: 0.5, y: 2.55, w: 9, h: 2.5, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("The safety is in code, not only in the prompt: Neo4j's read transaction is the real write guard, and the regex validator gives the LLM useful error messages for its one retry.");

  s = content("The evaluation drove the design", "Part E – AI");
  s.addChart(pres.charts.BAR, [
    { name: "10 tuning questions", labels: ["run 1", "run 2", "run 3", "run 4", "run 5", "run 6"], values: [2, 7, 8, 10, 8, 10] },
  ], { x: 0.4, y: 1.15, w: 5.2, h: 3.85, barDir: "col", chartColors: [H.accent1], valAxisMaxVal: 10, valAxisMinVal: 0, valAxisMajorUnit: 2,
    catAxisLabelColor: H.dk1, valAxisLabelColor: H.accent5, catAxisLabelFontSize: 11, valAxisLabelFontSize: 10, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    valGridLine: { color: H.lt2, size: 0.5 }, catGridLine: { style: "none" }, showLegend: false,
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: H.dk1, dataLabelFontSize: 11, dataLabelFontFace: "+mn-lt",
    showTitle: true, title: "Correct answers out of 10, per run", titleFontSize: 13, titleColor: H.dk2, titleFontFace: "+mn-lt" });
  s.addText([
    { text: "4 / 5", options: { bold: true, fontSize: 40, color: C.accent1, fontFace: THEME.headFontFace, breakLine: true } },
    { text: "on unseen questions, read by hand (the automatic check said 5 / 5)", options: { bold: true, fontSize: 14, breakLine: true } },
    { text: " ", options: { fontSize: 8, breakLine: true } },
    { text: "Run 5's held-out 2/5 showed overfitting; fixes were made by failure type, then a fresh held-out set was written.", options: { fontSize: 14, breakLine: true } },
    { text: " ", options: { fontSize: 8, breakLine: true } },
    { text: "No answer in any run contained an invented fact.", options: { fontSize: 14, bold: true, color: C.text2 } },
  ], { x: 5.9, y: 1.25, w: 3.6, h: 3.7, color: C.text1, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("Tell the story: 2/10 with gpt-4o-mini and a thin prompt; real relationship patterns, worked examples and direction checks took it to 7; the supplier-lot cause was missing from the graph itself (8 → 10). Then held-out 2/5 exposed overfitting, so fixes were made only by failure type, and a fresh held-out set passed 5/5 automatically, but reading the answers showed one led with a routine PM order instead of the repair: honestly 4/5. Run 5 also showed randomness, fixed with temperature 0.");

  // ============================================================ wrap-up
  pres.addSection({ title: "Wrap-up" });
  s = content("Limits I state up front", "Wrap-up");
  const lim = [
    [md.MdScience, "Synthetic, TRAIN-only scores", "the hidden test set is the real measure"],
    [md.MdTune, "Thresholds from little data", "one more error would move the WO threshold"],
    [md.MdPendingActions, "Root causes in review", "4 of 8 root-cause WOs wait for an engineer"],
    [md.MdSchedule, "Inferred reads after buffers", "up to 69 min off; flagged with uncertainty"],
    [md.MdHelpOutline, "Causes are hypotheses", "lot cause needs a defect-to-part map; E3 not attempted"],
    [md.MdCloudOff, "GraphRAG: lenient check, OpenAI", "automatic 5/5 was 4/5 by hand; data sent out"],
  ];
  for (let i = 0; i < lim.length; i++) {
    const x = 0.5 + (i % 2) * 4.6, y = 1.2 + Math.floor(i / 2) * 1.2;
    await iconCircle(s, lim[i][0], x, y + 0.08, 0.5, C.accent2, `${lim[i][1]} icon`);
    s.addText([{ text: lim[i][1], options: { bold: true, breakLine: true } }, { text: lim[i][2] }],
      { x: x + 0.65, y, w: 3.8, h: 0.95, fontSize: 14, color: C.text1, valign: "top", margin: 0, isTextBox: true });
  }
  s.addNotes("Interview Q4: why might it score lower on real data? Real naming is less regular, labels are noisier, new lines appear. How to find out: label 200 random records per source and plant, and track the precision of auto-accepted links monthly.");

  s = content("At 10 plants and 2 M VINs a year", "Wrap-up");
  const sc = [
    [md.MdStorage, "Split the storage", "Graph keeps assets, tags, WOs, defects, lots, anomalies. Per-station passages (~80 M a year) go to partitioned Parquet/Delta, like time-series values."],
    [md.MdSchool, "Per-plant matching", "Parser rules as plant config; retrain per plant with active learning; review queue ordered by value."],
    [md.MdSync, "Stream and govern", "OPC UA / MQTT → Kafka; real MES times replace takt inference; versioned ontology; LLM in the company tenant."],
  ];
  for (let i = 0; i < sc.length; i++) {
    const x = 0.5 + i * 3.05;
    card(s, x, 1.25, 2.9, 3.45, `scale card ${i + 1}`);
    await iconCircle(s, sc[i][0], x + 0.2, 1.45, 0.55, C.accent1, `${sc[i][1]} icon`);
    s.addText(sc[i][1], { x: x + 0.2, y: 2.12, w: 2.5, h: 0.45, fontSize: 16, bold: true, color: C.text2, margin: 0, isTextBox: true });
    s.addText(sc[i][2], { x: x + 0.2, y: 2.6, w: 2.5, h: 2.0, fontSize: 14, color: C.text1, valign: "top", margin: 0, isTextBox: true });
  }
  s.addText("In Cognite: spaces + DMS for structure, the time-series API for values, Atlas AI for agents. The design maps one to one.",
    { x: 0.5, y: 4.8, w: 9, h: 0.35, fontSize: 12, italic: true, color: C.accent5, margin: 0, isTextBox: true });
  s.addNotes("Interview Q2 (scale) and Q7 (Cognite). With my own stack I lose Cognite's managed extractors, diagram parsing, access control and Atlas AI. I gain transparency, cost control and no lock-in, at the price of operating it myself.");

  // ============================================================ live demo
  pres.addSection({ title: "Live demo and code" });
  s = content("Live demo: four things to show", "Live demo and code");
  const demo = [
    [md.MdTerminal, "python -m ddn.demo tag DDN1_BIW_L2_R07_WELDCUR.PV", "raw tag → parsed → matched → graph edge with provenance"],
    [md.MdDirectionsCar, "python -m ddn.demo vin", "one car: stations, robots, torque, lots, defect → cause → work order"],
    [md.MdFactCheck, "streamlit run apps/review_app.py", "approve or correct a link; it becomes an engineer edge and a label"],
    [md.MdQuestionAnswer, "streamlit run apps/ask_app.py", "a cited answer, its Cypher, and an honest \"I don't know\""],
  ];
  for (let i = 0; i < demo.length; i++) {
    const y = 1.2 + i * 0.92;
    await iconCircle(s, demo[i][0], 0.5, y + 0.05, 0.55, C.accent1, `demo ${i + 1} icon`);
    s.addText([{ text: demo[i][1], options: { fontFace: "Courier New", bold: true, color: C.text2, fontSize: 14, breakLine: true } },
      { text: demo[i][2], options: { fontSize: 14, color: C.text1 } }],
      { x: 1.25, y, w: 8.25, h: 0.8, valign: "middle", margin: 0, isTextBox: true });
  }
  s.addText("Before the interview: run_all once, start Neo4j, open both Streamlit screens after the last git pull.",
    { x: 0.5, y: 4.85, w: 9, h: 0.3, fontSize: 11, italic: true, color: C.accent5, margin: 0, isTextBox: true });
  s.addNotes("Keep each demo to 2 minutes. In the review screen, approve the first item (it explains anomaly AN-003). In the ask screen, ask the cold-weld question, open the Cypher expander, then ask the shift-supervisor question to show 'I don't know'.");

  s = content("Code walkthrough: where to look", "Live demo and code");
  table(s, [
    ["File", "Open it to show"],
    ["src/ddn/pipeline.py", "the 17 steps in order: one list used by make all and run_all"],
    ["src/ddn/match_ml.py", "CandidateGenerator (blocking), pair_features(), cross_validate(), thresholds()"],
    ["src/ddn/review.py, apps/review_app.py", "review queue, decisions.csv, decisions reused as labels"],
    ["ontology/ontology_v1.yaml", "node and edge types, provenance, views, changelog"],
    ["src/ddn/graph.py", "prov() on every edge, approved_links(), validate_graph()"],
    ["src/ddn/queries.py", "the seven Cypher queries D1–D7"],
    ["src/ddn/anomaly.py", "robust_z(), alarm_windows(), judge()"],
    ["src/ddn/graphrag.py", "validate(), run_read(), ground(), expand()"],
  ], { x: 0.5, y: 1.2, w: 9, colW: [3.4, 5.6], fontSize: 13, rowH: 0.42 });
  s.addNotes("Let them choose. For 'walk through one work order' (question 1) open textnorm.extract, then match_ml features, then the review screen. For 'why does the graph think this' open graph.prov and show an edge's evidence in the Neo4j browser.");

  s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Wrap-up" });
  s.addText("Working, measured, honest", { placeholder: "title" });
  s.addText([
    { text: "github.com/akashnegetive/Industrial-AI-Automobile-Manufacturing-Plant", options: { breakLine: true } },
    { text: "Live: python -m ddn.demo tag · python -m ddn.demo vin · streamlit run apps/ask_app.py", options: { fontSize: 14, color: C.accent1 } },
  ], { placeholder: "body" });
  s.addNotes("Close with the rubric's own phrase: working, honest, measured code. Offer the code walkthrough: pipeline.py for the step list, match_ml.py for features and thresholds, graph.py for provenance, graphrag.py for the validator and grounding.");

  // ============================================================ backup
  pres.addSection({ title: "Backup – interview questions" });
  const qa = [
    ["Work order → edge, where can it go wrong?", "Normalise, extract, match, gate, review. Risks: robot vs gun vs tip dresser, missing line, misread Hinglish, SAP code contradicting the text."],
    ["Property graph or RDF? At 10 plants?", "Property graph: edge properties are native, Cypher is easy to validate. RDF for cross-company semantics. Scale by moving passages to columnar storage."],
    ["How was the auto threshold set?", "Lowest out-of-fold score with precision ≥ 0.995 and no wrong-machine error. A wrong link in a recall costs more than a review."],
    ["Why might real data score lower?", "Less regular names, noisier labels, new lines. Measure with a labelled random sample per plant; monitor auto-link precision."],
    ["Robot moved from Line 2 to Line 3?", "partOf has valid_from / valid_to; VIN queries use the edge valid at the VIN's time."],
    ["What did the AI assistant write?", "Drafts of code, tests and docs (docs/AI_USAGE.md). I ran every step, checked numbers against the reports, and the tests pin the results."],
    ["Mapping onto Cognite?", "Ontology = containers + views; FL = externalId; provenance = annotation confidence + status; Parquet = time-series API."],
  ];
  for (const [part, items] of [[1, qa.slice(0, 4)], [2, qa.slice(4)]]) {
    s = content(`Backup: interview questions (${part}/2)`, "Backup – interview questions");
    items.forEach((q, i) => {
      const y = 1.2 + i * 0.95;
      num(s, (part - 1) * 4 + i + 1, 0.5, y + 0.05, 0.38);
      s.addText([{ text: q[0], options: { bold: true, color: C.text2, breakLine: true } }, { text: q[1] }],
        { x: 1.05, y, w: 8.45, h: 0.88, fontSize: 14, color: C.text1, valign: "top", margin: 0, isTextBox: true });
    });
    s.addNotes("Backup slides: only show if the question comes up. The answers are short on purpose; expand verbally.");
  }

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote " + OUT);
})();
