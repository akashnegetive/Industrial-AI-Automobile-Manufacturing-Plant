# Day 3 – Vendor research (Part A) and ontology (Part D design)

| Deliverable | File |
|---|---|
| Part A research draft | `docs/part_a_research.md` |
| Ontology (versioned YAML) | `ontology/ontology_v1.yaml` |
| Validator + doc generator | `src/ddn/ontology.py` → `docs/ontology.md` |
| Tests | `tests/test_ontology.py` |

Run: `make ontology` (validate and render) or `make all`.

---

## 1. Part A research – status and what to do

The draft covers every row the assignment asks for: modelling, linking, confidence, standards, GenAI, values vs metadata, limits, automotive use cases, and borrowed ideas. It compares **Cognite**, **Siemens** and **AWS IoT TwinMaker**.

**Why AWS as the third platform:** it has a documented knowledge graph with a query language (PartiQL `MATCH`) and an official automotive story (the Volkswagen Digital Production Platform). No official Azure Digital Twins automotive-plant story turned up.

**Open items (manual work):**
1. The vendor sites were blocked from the build environment, so the draft is based on search-engine extracts. **Open every link** and check each sentence against the page. Fix or remove anything that doesn't match.
2. Claims marked ⚠ have no official source. Either find one or keep them marked as gaps. The assignment rewards stating a gap honestly over guessing.
3. Known gaps: no Cognite automotive customer; no Siemens AAS support documented inside Insights Hub (the AAS product is SITRANS assetfox); the VW case is AWS industrial cloud in general, not TwinMaker specifically.
4. Length: the assignment asks for 3–4 pages. The tables are dense; expand the prose where your own reading adds detail.

## 2. The ontology – design decisions

### Why YAML plus a validator
The ontology is the **contract** between every later step: the matcher produces edges of these types, the loader creates exactly these labels and constraints, and the GraphRAG prompt describes exactly this schema. Keeping it in one versioned file, and failing loudly when it's inconsistent, stops those three from drifting apart.

`ontology.py` does three things:
1. `parse_props` turns `string!` into `Prop(type="string", required=True)` and rejects unknown types. A typo like `strng` fails instead of being silently accepted.
2. `validate` checks: the assignment's minimum node and edge types are present; every edge points at existing node types; every key property is required; the provenance fields are mandatory; views and indexes only reference real properties.
3. `to_markdown` renders `docs/ontology.md` with a Mermaid diagram, which GitHub draws automatically. `schema_summary` produces the compact schema the LLM will receive on Day 9.

### Property graph (Neo4j) rather than RDF
- The key questions are **paths with time filters**: VIN → station → equipment → signal window.
- A property graph stores time, confidence and provenance **directly on the edge**. RDF needs reification or RDF-star for the same thing.
- Cypher is widely used, so LLMs generate it reliably (important for E2).
- Trade-off accepted: no built-in OWL reasoning and no direct AAS/RDF export. An RDF export could be added later for AAS alignment.

### Choices driven by this plant's data
| Decision | Reason from the data |
|---|---|
| `partOf` is **time-valid** (`valid_from`/`valid_to`) | Robot RB12 moved from L1-ST03 to L2-ST06 in Mar 2026. Cars built before and after must link to the right station. |
| `Station.mes_code` as an alias property | MES `B2-04` and SAP `DDN1-BIW-L2-ST04` are the same place. One node, two identities. |
| `Equipment.aliases` list | Keeps every name seen (R07, RB-207, BIW/L2/S4/RB07) for search and GraphRAG. |
| `passedThrough.inferred` | Reader RD-SLR-2 was offline; inferred passages must stay distinguishable. |
| `Part` = one node per fitted part (`vin|part_no`) | Each fitted part links to exactly one lot, which the recall query needs. |
| `SupplierLot` also holds press batches | Body panels trace to `PB-PL1-…` batches the same way as supplier lots. |
| `causedBy` never uses `method=source_key` | No source system records causes; every cause is derived or engineer-approved. |
| `aliasOf` edge between time series | Legacy tag `DDN1_BIW_L1ST3_RB5_*` points to the robot's current identity. |
| Extra `AnomalyEvent` node | Part E1 writes detections into the graph as events on equipment. |

### Provenance on every edge
`source_system`, `method`, `confidence`, `created_at` and `status` are required. `status` copies Cognite's `CogniteAnnotation` values (suggested / approved / rejected). This turns "why does the graph think this?" into a property lookup.

### Containers vs views (the Cognite mapping)
- **Container** = how data is stored. In Neo4j that's a label, its properties, and its uniqueness and range indexes.
- **View** = what a role sees. Three views are defined: *Maintenance*, *Quality*, *Traceability*. Each lists the node properties and edges that audience uses.
- What would be lost compared with Cognite's managed DMS: built-in versioned views, access control per space, and managed scaling.

### Scale
7,200 VINs × ~44 stations ≈ 310k `passedThrough` edges (the assignment's case is 18,000 × 40 = 720k).
- VINs link to **46 station nodes**, not to every machine.
- `processedBy` is only materialised for equipment that touches the car (robots, sealers, nutrunners).
- Range indexes go on `passed_at` and `start`.
- Values never enter the graph.

## 3. Exercises
- Break the YAML on purpose (e.g. change `to: [Station]` to `to: [Stattion]` under `detectedAt`) and run `make ontology`. Read the error.
- Open `docs/ontology.md` on GitHub to see the rendered diagram.
- Write by hand the Cypher you'd expect for query D2 (water-leak VIN → sealer robot → nozzle temperature) using only the schema summary. Day 7 checks it against the real graph.
