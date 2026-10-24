"""Load, validate and document the ontology (ontology/ontology_v1.yaml).

The YAML is the single source of truth for the graph schema. This module:
1. parses it into pydantic models (typos in the file become clear errors),
2. checks consistency rules a hand-edited file easily breaks,
3. renders docs/ontology.md with tables and a Mermaid diagram.

Later code (graph loader, GraphRAG schema prompt) reads the same object, so the
schema the LLM sees is always the schema the loader enforces.

Run:  python -m ddn.ontology
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .config import ROOT

ONTOLOGY_FILE = ROOT / "ontology" / "ontology_v1.yaml"

# What the assignment (Part D) requires as a minimum.
REQUIRED_NODES = {"Site", "Shop", "Line", "Station", "Equipment", "Component", "Tool", "TimeSeries",
                  "WorkOrder", "FailureMode", "Document", "Alarm", "Vehicle", "Part", "SupplierLot",
                  "TorqueResult", "Defect"}
REQUIRED_EDGES = {"partOf", "hasTimeSeries", "hasWorkOrder", "reportsFailure", "mentionedIn", "feeds",
                  "passedThrough", "processedBy", "containsPart", "fromLot", "detectedAt", "causedBy"}

TYPE_RE = re.compile(r"^(string|int|float|bool|date|datetime|list\[string\])(!?)$")


class Prop(BaseModel):
    name: str
    type: str
    required: bool


def parse_props(raw: dict | None) -> list[Prop]:
    """'string!' -> Prop(type='string', required=True). Unknown types raise."""
    out = []
    for name, spec in (raw or {}).items():
        m = TYPE_RE.match(str(spec))
        if not m:
            raise ValueError(f"property {name!r}: unknown type {spec!r}")
        out.append(Prop(name=name, type=m.group(1), required=m.group(2) == "!"))
    return out


class NodeType(BaseModel):
    name: str
    isa95: str
    cognite: str
    key: str
    properties: list[Prop]
    description: str = ""
    example: str = ""


class EdgeType(BaseModel):
    name: str
    from_: list[str] = Field(alias="from")
    to: list[str]
    cardinality: str
    time_valid: bool = False
    properties: list[Prop] = []
    description: str = ""


class Ontology(BaseModel):
    version: str
    nodes: dict[str, NodeType]
    edges: dict[str, EdgeType]
    provenance: dict[str, dict]
    views: dict[str, dict]
    containers: dict
    raw: dict

    def node_props(self, label: str) -> set[str]:
        return {p.name for p in self.nodes[label].properties}


def load_ontology(path: Path = ONTOLOGY_FILE) -> Ontology:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    nodes = {n: NodeType(name=n, **{**spec, "properties": parse_props(spec.get("properties"))})
             for n, spec in raw["node_types"].items()}
    edges = {e: EdgeType(name=e, **{**spec, "properties": parse_props(spec.get("properties"))})
             for e, spec in raw["edge_types"].items()}
    return Ontology(version=str(raw["version"]), nodes=nodes, edges=edges, provenance=raw["provenance"],
                    views=raw["views"], containers=raw["containers"], raw=raw)


def validate(o: Ontology) -> list[str]:
    """Return a list of problems; an empty list means the ontology is consistent."""
    errors = []
    errors += [f"missing required node type {n}" for n in REQUIRED_NODES - o.nodes.keys()]
    errors += [f"missing required edge type {e}" for e in REQUIRED_EDGES - o.edges.keys()]

    for n in o.nodes.values():
        key = next((p for p in n.properties if p.name == n.key), None)
        if key is None or not key.required:
            errors.append(f"{n.name}: key {n.key!r} must be a required property")

    for e in o.edges.values():
        for label in e.from_ + e.to:
            if label not in o.nodes:
                errors.append(f"edge {e.name}: unknown node type {label}")
        if e.cardinality not in {"one", "many"}:
            errors.append(f"edge {e.name}: cardinality must be one/many")

    for p in ("source_system", "method", "confidence", "created_at", "status"):
        if not o.provenance.get(p, {}).get("required"):
            errors.append(f"provenance property {p} must be required on every edge")

    for vname, v in o.views.items():
        for label, props in v["nodes"].items():
            if label not in o.nodes:
                errors.append(f"view {vname}: unknown node type {label}")
                continue
            errors += [f"view {vname}: {label}.{p} not defined" for p in props if p not in o.node_props(label)]
        errors += [f"view {vname}: unknown edge {e}" for e in v["edges"] if e not in o.edges]

    for idx in o.containers.get("indexes", []):
        if "label" in idx and idx["property"] not in o.node_props(idx["label"]):
            errors.append(f"index on unknown property {idx['label']}.{idx['property']}")
        if "rel" in idx and idx["property"] not in {p.name for p in o.edges[idx["rel"]].properties}:
            errors.append(f"index on unknown edge property {idx['rel']}.{idx['property']}")
    return errors


def schema_summary(o: Ontology) -> str:
    """Compact text schema. Reused later as the LLM prompt for Cypher generation (Part E2)."""
    lines = ["Node labels (key property first):"]
    for n in o.nodes.values():
        props = [n.key] + [p.name for p in n.properties if p.name != n.key]
        lines.append(f"  (:{n.name} {{{', '.join(props)}}})")
    lines.append("Relationships (every one also has source_system, method, confidence, created_at, status):")
    for e in o.edges.values():
        props = [p.name for p in e.properties] + (["valid_from", "valid_to"] if e.time_valid else [])
        extra = f" {{{', '.join(props)}}}" if props else ""
        lines.append(f"  ({'|'.join(e.from_)})-[:{e.name}{extra}]->({'|'.join(e.to)})")
    return "\n".join(lines)


def to_markdown(o: Ontology) -> str:
    out = [f"# Ontology v{o.version}", "",
           "Generated by `python -m ddn.ontology` from `ontology/ontology_v1.yaml`. Do not edit by hand.", "",
           f"**Storage:** {o.raw['storage']['graph']}; time series in {o.raw['storage']['timeseries']}.", "",
           f"*Why a property graph:* {o.raw['storage']['rationale'].strip()}", "",
           "## Diagram", "", "```mermaid", "graph LR"]
    seen = set()
    for e in o.edges.values():
        for a in e.from_:
            for b in e.to:
                if (a, b, e.name) not in seen:
                    seen.add((a, b, e.name))
                    out.append(f"  {a} -->|{e.name}| {b}")
    out += ["```", "", "## Node types", "",
            "| Node | ISA-95 level | Cognite view | Key | Properties (* = required) | Example |",
            "|---|---|---|---|---|---|"]
    for n in o.nodes.values():
        props = ", ".join(p.name + ("*" if p.required else "") for p in n.properties)
        out.append(f"| **{n.name}** | {n.isa95} | {n.cognite} | `{n.key}` | {props} | `{n.example}` |")
    out += ["", "## Edge types", "",
            "| Edge | From | To | Card. | Time-valid | Extra properties | Meaning |", "|---|---|---|---|---|---|---|"]
    for e in o.edges.values():
        props = ", ".join(p.name for p in e.properties) or "—"
        out.append(f"| **{e.name}** | {', '.join(e.from_)} | {', '.join(e.to)} | {e.cardinality} | "
                   f"{'yes' if e.time_valid else ''} | {props} | {e.description.strip()} |")
    out += ["", "## Provenance (on every edge)", "", "| Property | Type | Values |", "|---|---|---|"]
    for k, v in o.provenance.items():
        vals = ", ".join(v.get("values", [])) or (f"{v.get('min')}–{v.get('max')}" if "min" in v else "")
        out.append(f"| `{k}` | {v['type']}{' (required)' if v.get('required') else ''} | {vals} |")
    out += ["", "## Containers and views (Cognite mapping)", "",
            o.containers["description"].strip(), "",
            "| View | Audience | Node types | Edges |", "|---|---|---|---|"]
    for name, v in o.views.items():
        out.append(f"| {name} | {v['audience']} | {', '.join(v['nodes'])} | {', '.join(v['edges'])} |")
    out += ["", "## Time validity", "", o.raw["temporal"]["description"].strip(), "",
            "## Keeping it fast", "", f"- This pack: {o.raw['scale']['this_pack']}",
            f"- Assignment scale: {o.raw['scale']['assignment_case']}"]
    out += [f"- {s}" for s in o.raw["scale"]["strategies"]]
    out += ["", "## Schema as the LLM will see it", "", "```", schema_summary(o), "```", ""]
    return "\n".join(out)


def main() -> None:
    o = load_ontology()
    errors = validate(o)
    if errors:
        raise SystemExit("ontology invalid:\n  " + "\n  ".join(errors))
    path = ROOT / "docs" / "ontology.md"
    path.write_text(to_markdown(o), encoding="utf-8")
    print(f"ontology v{o.version} valid: {len(o.nodes)} node types, {len(o.edges)} edge types -> {path}")


if __name__ == "__main__":
    main()
