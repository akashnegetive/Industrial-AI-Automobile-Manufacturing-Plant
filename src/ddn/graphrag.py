"""Part E2 - natural-language Q&A over the graph (GraphRAG), grounded and cited.

    question --(LLM)--> Cypher --(validate)--> read-only run --> rows --(LLM)--> cited answer

Safety and grounding are enforced in code, not only asked for in the prompt:
  1. The LLM sees the ontology schema (ddn.ontology.schema_summary) and must return JSON
     {can_answer, reason, cypher} (structured output).
  2. validate(): read-only keywords only; every label, relationship type and property must exist
     in the ontology; EXPLAIN must accept it; a LIMIT is added. One retry with the error message.
  3. The query runs in a READ transaction with a timeout (Neo4j itself refuses writes there).
  4. No rows -> "I don't know" (the LLM is not asked to guess).
  5. The LLM writes the answer from the rows only, as sentences with citations. Every citation must
     be an identifier that appears in the rows; a sentence with no valid citation is DROPPED.
     Nothing left -> "I don't know".  (No citation, no claim.)

Providers (DDN_LLM=openai|anthropic|ollama|offline; default: first one that is configured)
  openai     OPENAI_API_KEY, model DDN_LLM_MODEL (default gpt-4o; gpt-4o-mini scored much lower)
  anthropic  ANTHROPIC_API_KEY, model claude-opus-5-5
  ollama     local Ollama at OLLAMA_URL (default http://localhost:11434), model DDN_LLM_MODEL (default qwen2.5-coder:7b)
  offline    no LLM: question templates mapped to fixed Cypher. A baseline so the pipeline and
             tests run anywhere - it is NOT GraphRAG and the report says so.

Run:  python -m ddn.graphrag ask "Why did water-leak defects rise on Line 2 last Tuesday?"
      python -m ddn.graphrag            (10-question evaluation -> reports/14_graphrag.md)
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime

from neo4j import unit_of_work

from .config import REPORTS
from .graph import driver
from .ontology import load_ontology, schema_summary

TODAY = date(2026, 9, 15)            # the data ends on 14 Sep; questions are asked "the next day"
ROW_LIMIT, ROWS_TO_LLM, TIMEOUT_S, MAX_ATTEMPTS = 100, 60, 10, 3

CYPHER_SCHEMA = {
    "type": "object",
    "properties": {"can_answer": {"type": "boolean"}, "reason": {"type": "string"}, "cypher": {"type": "string"}},
    "required": ["can_answer", "reason", "cypher"], "additionalProperties": False,
}
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "dont_know": {"type": "boolean"},
        "sentences": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "citations": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "citations"], "additionalProperties": False}},
    },
    "required": ["dont_know", "sentences"], "additionalProperties": False,
}


# ------------------------------------------------------------------ providers
class OpenAIProvider:
    name = "openai"

    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI()                                   # reads OPENAI_API_KEY
        self.model = os.getenv("DDN_LLM_MODEL", "gpt-4o")

    def json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        # temperature 0 + fixed seed: the same question gives (almost) the same query every run. Reasoning
        # models (o1/o3/o4, gpt-5) don't accept a temperature, so it is left out for them.
        fixed = {} if self.model.startswith(("o1", "o3", "o4", "gpt-5")) else {"temperature": 0, "seed": 7}
        r = self.client.chat.completions.create(
            model=self.model, **fixed,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": schema_name, "strict": True, "schema": schema}})
        msg = r.choices[0].message
        if getattr(msg, "refusal", None):
            raise RuntimeError(f"model refused: {msg.refusal}")
        return json.loads(msg.content)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic()                      # reads ANTHROPIC_API_KEY / ant profile
        self.model = os.getenv("DDN_LLM_MODEL", "claude-opus-5-5")

    def json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        r = self.client.beta.messages.create(
            model=self.model, max_tokens=16000, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default")     # safety-decline fallback
        if r.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        return json.loads(next(b.text for b in r.content if b.type == "text"))


class OllamaProvider:
    name = "ollama"

    def __init__(self):
        self.url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = os.getenv("DDN_LLM_MODEL", "qwen2.5-coder:7b")

    def json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        body = json.dumps({"model": self.model, "stream": False, "format": schema, "options": {"temperature": 0},
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(f"{self.url}/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(json.loads(resp.read())["message"]["content"])


def _ollama_up() -> bool:
    try:
        urllib.request.urlopen(os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/tags", timeout=2)
        return True
    except Exception:
        return False


def get_provider():
    choice = os.getenv("DDN_LLM", "").lower()
    if choice == "offline":
        return None
    if choice == "openai" or (not choice and os.getenv("OPENAI_API_KEY")):
        return OpenAIProvider()
    if choice == "anthropic" or (not choice and os.getenv("ANTHROPIC_API_KEY")):
        return AnthropicProvider()
    if choice == "ollama" or (not choice and _ollama_up()):
        return OllamaProvider()
    return None


# ----------------------------------------------------------------- validator
FUNCTION_NAMESPACES = {"date", "datetime", "localdatetime", "duration", "time", "localtime", "point", "db"}
FORBIDDEN = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|FOREACH|CALL|USE|ALTER|GRANT|DENY|"
                       r"REVOKE|START|STOP|TERMINATE|SHOW|FINISH)\b", re.I)


class CypherRejected(ValueError):
    pass


def _strip_strings(q: str) -> str:
    return re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", "''", q)


def validate(cypher: str, session=None) -> str:
    """Return a safe, LIMITed query or raise CypherRejected with a reason the LLM can fix."""
    o = load_ontology()
    q = cypher.strip().rstrip(";")
    bare = _strip_strings(q)
    if ";" in bare:
        raise CypherRejected("only one statement is allowed")
    # property names (e.start), map keys ({start: ...}) and aliases (AS start ... ORDER BY start) are not keywords
    aliases = {a.lower() for a in re.findall(r"\bAS\s+([A-Za-z_]\w*)", bare, re.I)}
    words = re.sub(r"\.\s*[A-Za-z_]\w*|\bAS\s+[A-Za-z_]\w*|[A-Za-z_]\w*\s*:(?!:)", " ", bare, flags=re.I)
    bad = next((m for m in FORBIDDEN.finditer(words) if m.group(1).lower() not in aliases), None)
    if bad:
        raise CypherRejected(f"read-only queries only: '{bad.group(1)}' is not allowed")
    labels = set(o.nodes) | {"Asset"}
    rels = set(o.edges)
    for expr in re.findall(r"[\(\[]\s*(?:[A-Za-z_]\w*)?\s*:\s*([A-Za-z_][\w|:&!]*)", bare):
        for name in filter(None, re.split(r"[|:&!]", expr)):
            if name not in labels | rels:
                raise CypherRejected(f"unknown label or relationship type '{name}'")
    check_directions(bare, o)
    props = {p.name for n in o.nodes.values() for p in n.properties} | \
            {p.name for e in o.edges.values() for p in e.properties} | set(o.provenance) | {"valid_from", "valid_to"}
    used = {m.group(2) for m in re.finditer(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b", bare)
            if m.group(1).lower() not in FUNCTION_NAMESPACES}
    for inner in re.findall(r"[\(\[]\s*\w*\s*:\s*\w+\s*\{([^}]*)\}", bare):
        used |= set(re.findall(r"([A-Za-z_]\w*)\s*:", inner))
    unknown = sorted(used - props)
    if unknown:
        raise CypherRejected(f"unknown property: {', '.join(unknown)}")
    if not re.search(r"\bLIMIT\s+\d+\s*$", bare, re.I):
        q = f"{q} LIMIT {ROW_LIMIT}"
    if session is not None:
        try:
            session.run("EXPLAIN " + q).consume()
        except Exception as exc:                             # syntax or semantic error from Neo4j
            raise CypherRejected(f"Neo4j rejected the query: {str(exc)[:300]}") from exc
    return q


NODE = r"\(\s*(\w*)\s*(?::\s*([\w|:&]+))?[^()]*\)"
HOP = re.compile(NODE + r"\s*(<?)-\s*\[\s*\w*\s*:\s*(\w+)[^\]]*\]\s*-(>?)\s*(?=" + NODE + ")")


def check_directions(bare: str, o) -> None:
    """Each (a:A)-[:rel]->(b:B) must match the ontology's from/to for rel. Labels come from the node
    itself or from where the same variable was labelled elsewhere in the query; :Asset is not checked."""
    known: dict[str, set[str]] = {}
    for var, lab in re.findall(r"\(\s*(\w+)\s*:\s*([\w|:&]+)", bare):
        these = {x for x in re.split(r"[|:&]", lab) if x} - {"Asset"}
        if these and known.get(var) and not these & known[var]:
            raise CypherRejected(f"variable '{var}' is used for two different node types "
                                 f"({'|'.join(sorted(known[var]))} and {'|'.join(sorted(these))}); use another name")
        known.setdefault(var, set()).update(these)

    def labels(var, lab):
        out = {x for x in re.split(r"[|:&]", lab or "") if x} - {"Asset"}
        return out or known.get(var, set())

    for m in HOP.finditer(bare):
        lv, ll, left_arrow, rel, right_arrow, rv, rl = m.groups()
        if rel not in o.edges or bool(left_arrow) == bool(right_arrow):
            continue
        a, b = labels(lv, ll), labels(rv, rl)
        if left_arrow:
            a, b = b, a
        e = o.edges[rel]
        if (a and not a & set(e.from_)) or (b and not b & set(e.to)):
            raise CypherRejected(
                f"({'|'.join(sorted(a)) or '?'})-[:{rel}]->({'|'.join(sorted(b)) or '?'}) does not exist: "
                f"{rel} goes ({'|'.join(e.from_)})-[:{rel}]->({'|'.join(e.to)}). Check the arrow direction.")


def run_read(session, q: str) -> list[dict]:
    @unit_of_work(timeout=TIMEOUT_S)                         # server-side time limit for the query
    def work(tx):
        return [{k: _plain(v) for k, v in r.items()} for r in tx.run(q)]
    return session.execute_read(work)


def _plain(v):
    if hasattr(v, "to_native"):
        v = v.to_native()
    if isinstance(v, (datetime, date)):
        return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
    if isinstance(v, list):
        return [_plain(x) for x in v]
    if hasattr(v, "items"):                                  # node / relationship -> its properties
        return {k: _plain(x) for k, x in dict(v).items()}
    return v


# ------------------------------------------------------------ evidence expansion
def _scalars(rows) -> set[str]:
    out = set()
    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            out.add(v)
    walk(rows)
    return out


def expand(session, rows: list[dict]) -> list[dict]:
    """Add the one-hop context the LLM's query may have left out, by fixed (not LLM-written) queries:
    for an anomaly, the asset it happened on and its work order; for a lot, the defects attributed to it.
    The answer is then grounded on rows + context."""
    vals = _scalars(rows)
    anomalies = sorted(v for v in vals if re.fullmatch(r"AN-\d{3}", v))
    lots = sorted(vals & {r["l"] for r in session.run("MATCH (:Defect)-[:causedBy]->(l:SupplierLot) "
                                                       "RETURN DISTINCT l.lot_id AS l")})
    ctx = []
    if anomalies:
        ctx += run_read(session, f"""MATCH (e:AnomalyEvent) WHERE e.anomaly_id IN {anomalies}
OPTIONAL MATCH (eq:Asset)-[:hasEvent]->(e)
OPTIONAL MATCH (w:WorkOrder {{wo_number: e.confirming_wo}})
RETURN 'anomaly' AS context, e.anomaly_id AS anomaly_id, eq.fl AS fl, eq.asset_type AS asset_type,
       e.judged AS judged, w.wo_number AS wo_number, w.short_text AS wo_text""")
    if lots:
        ctx += run_read(session, f"""MATCH (d:Defect)-[c:causedBy]->(l:SupplierLot) WHERE l.lot_id IN {lots}
RETURN 'supplier lot root cause' AS context, l.lot_id AS lot_id, l.part_no AS part_no, l.supplier AS supplier,
       d.defect_code AS defect_code, count(d) AS defects_attributed, head(collect(c.evidence)) AS evidence,
       head(collect(c.status)) AS status""")
    return ctx


# ----------------------------------------------------------------- grounding
def _norm(v) -> str:
    s = str(v).strip().strip("`'\"").lower()
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?|-?\d+(\.\d+)?", s):      # 1,785 / 1785.0 -> 1785
        f = float(s.replace(",", ""))
        s = str(int(f)) if f == int(f) else str(f)
    return s


def citable(rows: list[dict], cypher: str | None = None) -> set[str]:
    """Every scalar in the rows can be cited (IDs, codes, names, numbers). So can a string literal the
    query filtered on, because rows came back: the lot ID in {lot_id: 'WS-260904-B'} was matched."""
    out = {_norm(x) for x in re.findall(r"'([^']+)'", cypher or "")} if rows else set()
    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif v is not None and str(v).strip():
            out.add(_norm(v))
    walk(rows)
    return out


def ground(sentences: list[dict], rows: list[dict], cypher: str | None = None) -> tuple[list[dict], int]:
    """Keep only sentences whose citations all appear in the rows (and that cite at least one)."""
    ok_ids = citable(rows, cypher)
    texts = " ".join(v for v in ok_ids if " " in v)          # longer text values, e.g. an anomaly's reason

    def found(c) -> bool:
        c = _norm(c)
        return c in ok_ids or (len(c) >= 4 and re.search(rf"(?<![\w-]){re.escape(c)}(?![\w-])", texts) is not None)

    kept, dropped = [], 0
    for s in sentences:
        cites = [c for c in s.get("citations", []) if found(c)]
        if cites and len(cites) == len(s.get("citations", [])):
            kept.append({"text": s["text"], "citations": cites})
        else:
            dropped += 1
    return kept, dropped


@dataclass
class Answer:
    question: str
    mode: str
    cypher: str | None = None
    rows: list[dict] = field(default_factory=list)
    sentences: list[dict] = field(default_factory=list)
    dont_know: bool = False
    reason: str = ""
    dropped_sentences: int = 0
    attempts: int = 0
    history: list[str] = field(default_factory=list)
    context: list[dict] = field(default_factory=list)         # facts added by expand(), not by the LLM's query          # rejected / empty queries before the final one

    def text(self) -> str:
        if self.dont_know:
            return f"I don't know. {self.reason}".strip()
        return " ".join(f"{s['text']} [{', '.join(s['citations'])}]" for s in self.sentences)


# ------------------------------------------------------------------- prompts
def value_hints(session) -> str:
    """Small catalogue of real values so the LLM writes correct filters (codes, verdicts, families)."""
    codes = [f"{r['c']} {r['d']}" for r in session.run(
        "MATCH (d:Defect) RETURN d.defect_code AS c, head(collect(DISTINCT d.defect_desc)) AS d ORDER BY c")]
    fam = [r["f"] for r in session.run("MATCH (d:Defect) RETURN DISTINCT d.defect_family AS f ORDER BY f")]
    verdicts = [r["j"] for r in session.run("MATCH (e:AnomalyEvent) RETURN DISTINCT e.judged AS j ORDER BY j")]
    lines = [f"{r['fl']} ({r['n']})" for r in session.run("MATCH (l:Line) RETURN l.fl AS fl, l.name AS n ORDER BY fl")]
    return (f"Defect codes: {'; '.join(codes)}\nDefect families: {', '.join(fam)}\n"
            f"AnomalyEvent.judged values: {', '.join(verdicts)}\nWorkOrder.wo_type: CM (repair), PM, CAL (calibration)\n"
            "Functional locations look like DDN1-<shop>-<line>-<station>-<equipment>[-<component>], e.g. "
            "DDN1-BIW-L1-ST01-RB01 (robot 1, body line 1, station 1), DDN1-PNT-OV1-Z1 (topcoat oven 1 zone 1), "
            "DDN1-PRS-PL1 (press line 1). Equipment codes: RB robot, SR sealer robot, NR nutrunner, Z oven zone, "
            "AHU air handling unit.\n"
            f"Lines and areas: {'; '.join(lines)}")


_PATTERNS: list[str] = []


def live_patterns(session) -> str:
    """Relationship patterns that really exist in the data, with counts (computed once per process).
    The ontology says what is allowed; this says what is there, e.g. Defect causedBy only AnomalyEvent."""
    if not _PATTERNS:
        _PATTERNS.extend(
            f"(:{r['f']})-[:{r['t']}]->(:{r['to']})  {r['n']:,}" for r in session.run(
                "MATCH (a)-[r]->(b) WITH [l IN labels(a) WHERE l <> 'Asset'][0] AS f, type(r) AS t, "
                "[l IN labels(b) WHERE l <> 'Asset'][0] AS to RETURN f, t, to, count(*) AS n ORDER BY t, f"))
        types = [r["t"] for r in session.run("MATCH (a:Asset) RETURN DISTINCT a.asset_type AS t ORDER BY t")]
        _PATTERNS.append("Asset.asset_type values: " + ", ".join(t for t in types if t))
    return "\n".join(_PATTERNS)


# Worked examples. They use other entities than the 10 evaluation questions, but they teach the same
# paths through the graph (that is their purpose); the report states this.
EXAMPLES = """\
Q: Which anomaly explains the cracked panels, and on which equipment? Was there a work order?
MATCH (d:Defect {defect_code: 'BP-031'})-[:causedBy]->(e:AnomalyEvent)<-[:hasEvent]-(eq:Asset)
OPTIONAL MATCH (w:WorkOrder {wo_number: e.confirming_wo})
RETURN eq.fl AS fl, eq.asset_type AS asset_type, e.anomaly_id AS anomaly_id, e.judged AS judged, e.reason AS reason,
       e.start AS start, e.end AS end, count(DISTINCT d) AS defects, w.wo_number AS wo_number, w.short_text AS wo_text

Q: Why were there so many alignment defects on 3 September?
MATCH (v:Vehicle)-[:hasDefect]->(d:Defect)
WHERE d.defect_family = 'alignment' AND date(d.detected_at) = date('2026-09-03')
OPTIONAL MATCH (d)-[:causedBy]->(e:AnomalyEvent)
OPTIONAL MATCH (d)-[:causedBy]->(l:SupplierLot)
RETURN d.defect_code AS defect_code, l.lot_id AS lot_id, e.anomaly_id AS anomaly_id,
       count(DISTINCT d) AS defects, collect(DISTINCT d.defect_id)[..5] AS defect_ids ORDER BY defects DESC

Q: How many vehicles got a battery from lot BT-260902-A, per day?
MATCH (l:SupplierLot {lot_id: 'BT-260902-A'})<-[:fromLot]-(:Part)<-[c:containsPart]-(v:Vehicle)
RETURN l.lot_id AS lot_id, date(c.fitted_at) AS day, count(DISTINCT v) AS vehicles ORDER BY day

Q: Which robots processed vehicle MDDA5XK00D002432 in body line 1 station 1?
MATCH (v:Vehicle {vin: 'MDDA5XK00D002432'})-[p:processedBy]->(e:Asset)
WHERE e.asset_type = 'Robot' AND e.fl STARTS WITH 'DDN1-BIW-L1-ST01'
RETURN v.vin AS vin, e.fl AS fl, p.start AS start, p.inferred AS inferred ORDER BY start

Q: List the pressure sensors on Press Line 1.
MATCH (a:Asset)-[:partOf*0..4]->(:Asset {fl: 'DDN1-PRS-PL1'})
MATCH (a)-[:hasTimeSeries]->(t:TimeSeries {isa51_code: 'PT'})
RETURN a.fl AS fl, t.tag AS tag, t.unit AS unit ORDER BY fl

Q: Was the anomaly on press PL1 on 2 September real?
MATCH (eq:Asset)-[:hasEvent]->(e:AnomalyEvent)
WHERE eq.fl STARTS WITH 'DDN1-PRS-PL1' AND date(e.start) = date('2026-09-02')
RETURN eq.fl AS fl, e.anomaly_id AS anomaly_id, e.judged AS judged, e.reason AS reason, e.start AS start

Q: What did the operator eat for lunch? -> can_answer=false (no such data in the schema)"""


def cypher_prompt(session) -> str:
    return (f"You translate questions about car plant DDN-01 into ONE read-only Neo4j Cypher query.\n"
            f"Today is {TODAY:%A %d %B %Y}; the data covers 1-14 Sep 2026 (no production on Sundays).\n\n"
            f"GRAPH SCHEMA (use ONLY these labels, relationship types and properties):\n"
            f"{schema_summary(load_ontology())}\n"
            "Every plant asset (Site, Shop, Line, Station, Equipment, Component, Tool) also has the label :Asset and "
            "the properties fl and asset_type. Prefer (x:Asset) filtered on fl / asset_type to guessing whether "
            "something is Equipment or Component.\n\n"
            f"RELATIONSHIPS THAT EXIST IN THE DATA (direction matters, counts):\n{live_patterns(session)}\n\n"
            f"VALUES:\n{value_hints(session)}\n"
            "TimeSeries.isa51_code: TT temperature, PT pressure, FT flow, LT level, CT conductivity, AT analysis/"
            "humidity, IT current, ET voltage, ST speed, VT vibration, WT weight/force.\n\n"
            f"EXAMPLES:\n{EXAMPLES}\n\n"
            "RULES:\n"
            "- MATCH / OPTIONAL MATCH / WHERE / WITH / RETURN / ORDER BY / LIMIT only. Never write data.\n"
            "- Write values inline as literals. Dates: date(x.detected_at) = date('2026-09-08').\n"
            "- RETURN identifiers (vin, defect_id, wo_number, anomaly_id, fl, lot_id, tag) and use AS aliases.\n"
            "- When an AnomalyEvent is involved, also return the asset it happened on, (eq:Asset)-[:hasEvent]->(e) "
            "as fl, and its work order (w:WorkOrder {wo_number: e.confirming_wo}) as wo_number.\n"
            "- A vehicle went through a line if it passed one of the line's stations: "
            "(v)-[:passedThrough]->(s:Station) WHERE s.fl STARTS WITH 'DDN1-BIW-L2'. passedThrough to a :Line "
            "exists only for paint-shop lines. 'Line N' on its own means body line N (DDN1-BIW-LN).\n"
            "- Use a different variable name for every node. When you fix a query, keep the dates and values "
            "taken from the question.\n"
            "- Causes ARE in the graph: Defect-[:causedBy]->AnomalyEvent (AnomalyEvent.judged / reason / "
            "confirming_wo) and Defect-[:causedBy]->SupplierLot (a bad supplier lot). For a "
            "'why' question, return that evidence.\n"
            "- Set can_answer=false ONLY when the question needs a kind of data that is not in the schema at all "
            "(people, costs, measurements that are not listed properties). Otherwise always try a query. "
            "Time-series values are not in the graph (only the latest_value).")


ANSWER_SYSTEM = ("You answer a plant engineer's question using ONLY the query result rows and related facts given. "
                 "A lot with a 'supplier lot root cause' fact explains its defects; a status 'suggested' means it is "
                 "a hypothesis, say so. Write short "
                 "sentences. Every sentence must cite at least one identifier or value copied exactly from the "
                 "rows (e.g. a vin, defect_id, wo_number, anomaly_id, fl, lot_id, or a count). Name the supporting "
                 "evidence the rows contain (anomaly_id, wo_number, lot_id, fl) in your sentences. Citations are the raw "
                 "values only, never column names. Do not use outside knowledge. "
                 "If the rows do not answer the question, set dont_know=true and return no sentences.")


# ------------------------------------------------------------------ pipeline
def ask(question: str, provider=None, session=None) -> Answer:
    own = session is None
    drv = driver() if own else None
    session = drv.session() if own else session
    try:
        if provider is None:
            return offline_answer(question, session)
        ans = Answer(question, provider.name)
        system = cypher_prompt(session)
        user = question
        for attempt in range(1, MAX_ATTEMPTS + 1):
            ans.attempts = attempt
            plan = provider.json(system, user, CYPHER_SCHEMA, "cypher_plan")
            if not plan["can_answer"]:
                ans.dont_know, ans.reason = True, plan["reason"] or "The graph does not hold this information."
                return ans
            try:
                ans.cypher = validate(plan["cypher"], session)
            except CypherRejected as exc:
                ans.cypher, problem = plan["cypher"], f"was rejected: {exc}"
            else:
                ans.rows = run_read(session, ans.cypher)
                if ans.rows:
                    break
                problem = ("returned 0 rows. Check the relationship directions against RELATIONSHIPS THAT EXIST, "
                           "use :Asset with fl/asset_type, use values exactly as listed under VALUES, and "
                           "drop filters that are not needed. Keep the dates from the question")
            ans.history.append(f"{plan['cypher']}  -> {problem}")
            user = f"{question}\n\nYour previous query {problem}\nQuery was:\n{plan['cypher']}\nWrite a corrected query."
        if not ans.rows:
            ans.dont_know, ans.reason = True, f"No query returned data after {ans.attempts} attempts."
            return ans
        ans.context = expand(session, ans.rows)
        shown = ans.rows[:ROWS_TO_LLM]
        note = f"\n(Showing {len(shown)} of {len(ans.rows)} rows.)" if len(ans.rows) > len(shown) else ""
        ctx = (f"\nRelated facts from the graph (JSON):\n{json.dumps(ans.context, default=str)}"
               if ans.context else "")
        out = provider.json(ANSWER_SYSTEM, f"Question: {question}\nCypher: {ans.cypher}\nRows (JSON):\n"
                            f"{json.dumps(shown, default=str)}{note}{ctx}", ANSWER_SCHEMA, "grounded_answer")
        ans.sentences, ans.dropped_sentences = ground(out["sentences"], ans.rows + ans.context, ans.cypher)
        if out["dont_know"] or not ans.sentences:
            ans.dont_know, ans.sentences = True, []
            ans.reason = "The query result does not support a cited answer."
        return ans
    finally:
        if own:
            session.close()
            drv.close()


# --------------------------------------------------- offline template baseline
DEFECT_WORDS = [(r"crater", "PD-020"), (r"cold weld|undersize|weld nugget|chisel", "BW-017"),
                (r"panel split|crack|neck", "BP-031"), (r"wheel.?nut|low torque|torque", "AU-077"),
                (r"roof.?ditch", "WL-101")]
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_day(q: str) -> date | None:
    ql = q.lower()
    m = re.search(r"last (" + "|".join(WEEKDAYS) + r")", ql)
    if m:
        delta = (TODAY.weekday() - WEEKDAYS.index(m.group(1))) % 7 or 7
        return date.fromordinal(TODAY.toordinal() - delta)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")", ql)
    return date(2026, MONTHS[m.group(2)], int(m.group(1))) if m else None


def offline_answer(question: str, session) -> Answer:
    """Template baseline: fixed Cypher per question type, answers built from rows with citations."""
    q = question.lower()
    a = Answer(question, "offline")

    def finish(cypher: str, build) -> Answer:
        a.cypher = validate(cypher, session)
        a.rows = run_read(session, a.cypher)
        a.sentences = build(a.rows) if a.rows else []
        a.sentences, a.dropped_sentences = ground(a.sentences, a.rows, a.cypher)
        if not a.sentences:
            a.dont_know, a.reason = True, "The graph returned no data for this question."
        return a

    lot = re.search(r"\bWS-\d{6}-[AB]\b", question)
    vin = re.search(r"\bMDD[A-Z0-9]{13}\b", question)
    day = parse_day(question)
    if lot:
        return finish(f"""MATCH (l:SupplierLot {{lot_id: '{lot.group(0)}'}})<-[:fromLot]-(:Part)<-[c:containsPart]-(v:Vehicle)
OPTIONAL MATCH (v)-[:hasDefect]->(d:Defect {{defect_code: 'WL-104'}})
RETURN l.lot_id AS lot_id, date(c.fitted_at) AS fitted_on, count(DISTINCT v) AS vehicles, count(d) AS door_leaks
ORDER BY fitted_on""", lambda r: [
            {"text": f"{sum(x['vehicles'] for x in r)} vehicles received parts from lot {r[0]['lot_id']}.",
             "citations": [r[0]["lot_id"]]},
            *[{"text": f"Fitted on {x['fitted_on']}: {x['vehicles']} vehicles, {x['door_leaks']} door leaks.",
               "citations": [r[0]["lot_id"], x["fitted_on"]]} for x in r]])
    if vin and "sealer" in q:
        st = re.search(r"station\s*(\d)", q)
        stf = f" AND e.fl CONTAINS 'ST0{st.group(1)}'" if st else ""
        return finish(f"""MATCH (v:Vehicle {{vin: '{vin.group(0)}'}})-[p:processedBy]->(e:Asset)
WHERE e.asset_type = 'SealerRobot'{stf}
RETURN v.vin AS vin, e.fl AS fl, p.start AS start, p.inferred AS inferred ORDER BY start""", lambda r: [
            {"text": f"Sealer robot {x['fl']} processed it at {x['start']}"
                     + (" (passage inferred: the RFID read was missing)." if x["inferred"] else "."),
             "citations": [x["vin"], x["fl"]]} for x in r])
    if re.search(r"oven\s*2", q) and "temperature sensor" in q:
        return finish("""MATCH (a:Asset)-[:partOf*0..3]->(:Asset {fl: 'DDN1-PNT-OV2'})
MATCH (a)-[:hasTimeSeries]->(t:TimeSeries {isa51_code: 'TT'})
RETURN a.fl AS fl, t.tag AS tag, t.latest_value AS latest_value ORDER BY fl""", lambda r: [
            {"text": f"Topcoat Oven 2 has {len(r)} temperature sensors.", "citations": [x["tag"] for x in r]},
            *[{"text": f"{x['tag']} on {x['fl']} last read {x['latest_value']:.1f} C.",
               "citations": [x["tag"], x["fl"]]} for x in r]])
    if re.search(r"oven\s*2.*zone\s*3|zone\s*3.*oven\s*2", q):
        return finish("""MATCH (eq:Asset {fl: 'DDN1-PNT-OV2-Z3'})-[:hasEvent]->(e:AnomalyEvent)
RETURN eq.fl AS fl, e.anomaly_id AS anomaly_id, e.judged AS judged, e.reason AS reason, e.start AS start""", lambda r: [
            {"text": f"{x['anomaly_id']} on {x['fl']} (from {x['start']}) was judged {x['judged']}: {x['reason']}.",
             "citations": [x["anomaly_id"], x["fl"], x["judged"]]} for x in r])
    if "water" in q and "leak" in q and day:
        return finish(f"""MATCH (v:Vehicle)-[:hasDefect]->(d:Defect)
WHERE d.defect_family = 'water leak' AND date(d.detected_at) = date('{day.isoformat()}')
OPTIONAL MATCH (v)-[:containsPart]->(:Part {{part_no: 'DOOR_SEAL'}})-[:fromLot]->(l:SupplierLot)
OPTIONAL MATCH (d)-[:causedBy]->(e:AnomalyEvent)
RETURN d.defect_code AS defect_code, d.location AS location, l.lot_id AS lot_id, e.anomaly_id AS anomaly_id,
       count(d) AS defects, collect(d.defect_id)[..3] AS defect_ids ORDER BY defects DESC""", lambda r: [
            {"text": f"{x['defects']} {x['defect_code']} leaks at the {x['location']} on {day:%d %b} were on cars "
                     f"with door-seal lot {x['lot_id']}" + (f", explained by anomaly {x['anomaly_id']}." if x['anomaly_id'] else "."),
             "citations": [c for c in [x["lot_id"], x["anomaly_id"], *x["defect_ids"]] if c]}
            for x in r if x["defects"] >= 3 and x["lot_id"]])
    code = next((c for pat, c in DEFECT_WORDS if re.search(pat, q)), None)
    if code and re.search(r"cause|why|which|what", q):
        return finish(f"""MATCH (d:Defect {{defect_code: '{code}'}})-[:causedBy]->(e:AnomalyEvent)<-[:hasEvent]-(eq:Asset)
OPTIONAL MATCH (w:WorkOrder {{wo_number: e.confirming_wo}})
RETURN eq.fl AS fl, e.anomaly_id AS anomaly_id, e.start AS start, e.end AS end, count(DISTINCT d) AS defects,
       w.wo_number AS wo_number, w.short_text AS wo_text""", lambda r: [
            {"text": f"{x['defects']} {code} defects are explained by anomaly {x['anomaly_id']} on {x['fl']} "
                     f"({x['start']} to {x['end']})"
                     + (f"; work order {x['wo_number']}: {x['wo_text']}." if x["wo_number"] else "."),
             "citations": [c for c in [x["anomaly_id"], x["fl"], x["wo_number"]] if c]} for x in r])
    a.dont_know, a.reason = True, "Offline mode only answers known question types, and this is not one of them."
    return a


# ---------------------------------------------------------------- evaluation
EVAL = [
    ("Why did water-leak defects rise on Line 2 last Tuesday?", ["WS-260904-B"], False),
    ("Which robot caused the cold welds on 7 and 8 September, and which work order fixed it?",
     ["DDN1-BIW-L2-ST04-RB07", "4102961"], False),
    ("What caused the paint craters on 10 September?", ["DDN1-PNT-AHU-AHUTC2", "AN-006"], False),
    ("Which nutrunner caused the low wheel-nut torque defects?", ["DDN1-ASM-FN1-ST03-NR14", "AN-002"], False),
    ("How many vehicles received parts from supplier lot WS-260904-B?", ["1785"], False),
    ("Was the Oven 2 zone 3 over-temperature on 12 September a quality problem?", ["AN-008", "false_alarm"], False),
    ("Which sealer robots processed vehicle MDDA5XK0XD004375 in sealer station 2?",
     ["DDN1-PNT-SL-ST02-SR03", "DDN1-PNT-SL-ST02-SR04"], False),
    ("List the temperature sensors in Topcoat Oven 2.", ["PaintShop-OVN2-Z3-Temp"], False),
    ("What was the paint film thickness on vehicle MDDA5XK0XD004375?", [], True),
    ("Who was the shift supervisor on 9 September?", [], True),
]


# Held out: written after the prompt was tuned on EVAL, never used to change the prompt. They show
# whether the fixes generalise or only fit the 10 questions above.
HOLDOUT = [
    ("What caused the roof-ditch water leaks on 9 September?", ["DDN1-PNT-SL-ST02-SR03", "AN-004"], False),
    ("Was there a faulty sensor in the e-coat tank?", ["AN-007", "sensor_fault"], False),
    ("What was wrong with the AHU TC1 supply fan, and which work order dealt with it?", ["AN-005", "4102967"], False),
    ("How many vehicles were exposed to the weld-current anomaly AN-003?", ["663"], False),
    ("What was the energy cost of Oven 2 last week?", [], True),
]


def score(ans: Answer, expected: list[str], expect_idk: bool) -> bool:
    if expect_idk:
        return ans.dont_know and not ans.sentences
    blob = (ans.text() + " " + " ".join(c for s in ans.sentences for c in s["citations"])).lower()
    return not ans.dont_know and all(e.lower() in blob for e in expected)


def evaluate(provider=None, questions=EVAL) -> list[tuple]:
    with driver() as drv, drv.session() as s:
        return [(q, exp, idk, ans := ask(q, provider, s), score(ans, exp, idk)) for q, exp, idk in questions]


def _table(results: list[tuple]) -> list[str]:
    out = ["| # | Question | Expected | Answer | Pass |", "|---:|---|---|---|---|"]
    for i, (q, exp, idk, a, ok) in enumerate(results, 1):
        want = "I don't know" if idk else ", ".join(exp)
        out.append(f"| {i} | {q} | {want} | {a.text()[:240].replace('|', '/')} | {'yes' if ok else '**no**'} |")
    return out


def report(results: list[tuple], mode: str, holdout: list[tuple] | None = None) -> str:
    n = sum(r[4] for r in results)
    out = ["# Part E2 – GraphRAG: questions answered from the graph, with citations", "",
           f"Generated by `python -m ddn.graphrag`. **Mode: {mode}.** Score: **{n}/{len(results)}** "
           f"({sum(1 for r in results if r[2])} questions where the right answer is \"I don't know\").", ""]
    if mode.startswith("offline"):
        out += ["> Offline mode: no LLM was configured, so each question was mapped to a fixed Cypher template. "
                "This proves the validator, read-only execution and citation checks end to end, but it is **not** "
                "GraphRAG. Set `OPENAI_API_KEY` (or another provider, see the module docstring) and run again to "
                "evaluate the LLM.", ""]
    if not mode.startswith("offline"):
        out += [f"> The Cypher prompt holds the ontology schema, the relationship patterns found in the data, value "
                f"lists, and {EXAMPLES.count('Q:')} worked examples (see `EXAMPLES` in `graphrag.py`). The examples "
                "use other entities than these 10 questions but teach the same graph paths.", ""]
    out += _table(results)
    if holdout:
        out += ["", f"## Held-out questions: {sum(r[4] for r in holdout)}/{len(holdout)}", "",
                "Written after the prompt was tuned on the 10 questions above and never used to change it, so this "
                "is the fairer estimate of how the system does on new questions.", "", *_table(holdout)]
    out += ["", "## Details", ""]
    for i, (q, exp, idk, a, ok) in enumerate(results + (holdout or []), 1):
        out += [f"### {i}. {q}", "", f"- Mode {a.mode}, attempts {a.attempts}, rows {len(a.rows)}, "
                f"context rows added: {len(a.context)}, sentences dropped for missing/invalid citations: {a.dropped_sentences}"]
        for h in a.history:
            out += [f"- Earlier attempt: `{h[:400]}`"]
        if a.cypher:
            out += ["", "```cypher", a.cypher, "```"]
        out += ["", f"**Answer:** {a.text()}", ""]
    return "\n".join(out)


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "ask":
        p = get_provider()
        a = ask(" ".join(sys.argv[2:]), p)
        print(f"[{a.mode}] {a.text()}")
        if a.cypher:
            print("\nCypher:\n" + a.cypher)
        return
    provider = get_provider()
    mode = provider.name if provider else "offline"
    try:
        results = evaluate(provider)
        holdout = evaluate(provider, HOLDOUT) if provider else None
    except Exception as exc:                 # bad key, no credit, unknown model: keep run_all going
        if provider is None:
            raise
        print(f"LLM provider {mode} failed ({type(exc).__name__}: {str(exc)[:200]}) - falling back to offline")
        mode, results = f"offline (the {mode} call failed: {type(exc).__name__})", evaluate(None)
        holdout = None
    path = REPORTS / "14_graphrag.md"
    path.write_text(report(results, mode, holdout), encoding="utf-8")
    held = f", held-out {sum(r[4] for r in holdout)}/{len(holdout)}" if holdout else ""
    print(f"graphrag ({mode}): {sum(r[4] for r in results)}/{len(results)}{held} -> {path}")


if __name__ == "__main__":
    main()
