# Part A – How industrial platforms do contextualization

Comparison of **Cognite Data Fusion (CDF)**, **Siemens** (Insights Hub, Industrial Information Hub, Industrial Copilot) and **AWS IoT TwinMaker**, based on vendor documentation. Each claim links to the page it comes from.

> **Source status (draft, 23 Oct 2026).** This draft was compiled from search-engine extracts of the linked pages. The vendor sites could not be opened directly from the build environment. Before submission, every link must be opened and each claim checked against the live page. Claims marked ⚠ could not be confirmed from an official page.

---

## 1. How is the plant modelled?

**Cognite.** CDF stores data in a **Data Modeling Service (DMS)** with three schema elements. *Containers* hold the physical storage of properties, *views* are logical schemas that map container properties (and can rename them, combine several containers, and inherit from other views with `implements`), and *data models* group views for a purpose. All are scoped to a *space* ([Containers, views, data models](https://docs.cognite.com/cdf/dm/dm_concepts/dm_containers_views_datamodels)). Cognite ships a **Core Data Model** (`CogniteCore`, system space `cdf_cdm`). Every core concept, such as `CogniteAsset`, `CogniteEquipment`, `CogniteTimeSeries`, `CogniteFile` and `CogniteActivity`, has a matching container and view. `CogniteAsset` is central and carries parent, root and an automatically maintained path ([Core data model](https://docs.cognite.com/cdf/dm/dm_reference/dm_core_data_model)). Cognite's design guide recommends extending only the core views you will populate and using *direct relations* as the default relationship type ([Designing scalable data models](https://docs.cognite.com/cdf/dm/dm_guides/dm_designing_scalable_models)).

**Siemens.** In **Insights Hub** (formerly MindSphere), an *asset type* is built from *variables* and *aspects*, and it inherits both from its parent type. Assets take the structure of their type, and static variables cannot receive time-series data ([Asset Management Service](https://developer.siemens.com/insights-hub/docs/apis/advanced-assetmanagement/api-assetmanagement-overview.html)). For semantic models, **Industrial Information Hub (IIH) Semantics** exposes model and time-series data through a **GraphQL API backed by a knowledge graph** ([IIH overview](https://developer.siemens.com/industrial-information-hub/overview.html)). Siemens' enterprise knowledge-graph product, **Rapidminer Graph Studio**, is described as built on W3C-standard ontologies, linking PLM, ERP, MES and supply-chain data without copying it ([Graph Studio](https://www.siemens.com/en-us/products/rapidminer/graph-studio/), [Siemens knowledge graphs](https://www.siemens.com/en-us/solutions/data-analytics-artificial-intelligence/knowledge-graphs/)). ⚠ I found no Siemens documentation describing AAS support *inside Insights Hub*. Siemens' AAS offering is the separate SaaS **SITRANS assetfox**, which provides an AAS repository, registry and AASX server ([assetfox](https://www.siemens.com/en-us/products/sitrans/assetfox/)).

**AWS IoT TwinMaker.** Twins are *entities* with *components*. Every relationship property on a component becomes an edge of the **TwinMaker knowledge graph**, and `parentEntityId` hierarchies add `isChildOf` edges ([Knowledge graph](https://docs.aws.amazon.com/iot-twinmaker/latest/guide/tm-knowledge-graph.html)).

## 2. How are records linked?

| Method | Cognite | Siemens | AWS |
|---|---|---|---|
| Rules / regex | Regex rules and confirmed matches are checked **before** model predictions ([About entity matching](https://docs.cognite.com/cdf/integration/guides/contextualization/matching)) | Linking is mostly configuration in the asset model and IIH connectors ⚠ | Relationships are declared on components by the integrator |
| Fuzzy / ML matching | **Unsupervised** model (weighted average of field-similarity scores) by default; a **supervised** model is trained when `trueMatches` labels exist ([Entity matching API](https://docs.cognite.com/api-reference/concepts/20230101/entity-matching)) | No documented ML entity matcher found ⚠ | None built in |
| Diagram parsing | Detects tags, file references, symbols and connections in P&IDs. Raster files give tags only; vector files also give symbols and connections. Tag detection is GA, full parsing in preview ([Diagram parsing](https://docs.cognite.com/cdf/integration/guides/contextualization/diagram_parsing), [Parse diagrams](https://docs.cognite.com/cdf/integration/guides/contextualization/parse_diagrams)) | — | — |
| Manual review | Pipelines, quick match, and manual confirmation ([Match entities](https://docs.cognite.com/cdf/integration/guides/contextualization/match_entities/)) | — | — |

## 3. How is confidence handled?

Cognite is the most explicit:
- **Thresholds:** a pipeline uses a model match only if its score is above the threshold *and* the match is not in the rejected list. The SDK's `predict` takes `score_threshold` ([About entity matching](https://docs.cognite.com/cdf/integration/guides/contextualization/matching), [Python SDK contextualization](https://cognite-sdk-python.readthedocs-hosted.com/en/latest/contextualization.html)).
- **Human approval feeds back:** confirmed matches take priority over model predictions and are reused to improve later suggestions. `refit` retrains on old plus new true matches (same sources).
- **Annotation status:** in the core model, `CogniteAnnotation` has a `confidence` property and a `status` of *Suggested*, *Approved* or *Rejected*. The diagram UI shows suggested links in orange and verified links in blue, with bulk approve and reject ([Core data model](https://docs.cognite.com/cdf/dm/dm_reference/dm_core_data_model), [Interactive diagrams](https://docs.cognite.com/cdf/integration/guides/contextualization/interactive_diagrams)).

I found no equivalent confidence workflow in the Siemens or AWS documentation ⚠. There, links are configured, not predicted.

## 4. Which standards are used?

| Standard | Cognite | Siemens | AWS |
|---|---|---|---|
| ISA-95 | Asset hierarchy via `CogniteAsset` parent/path ([Build an asset hierarchy](https://docs.cognite.com/cdf/dm/dm_guides/dm_cdm_build_asset_hierarchy)) | Asset hierarchy in Insights Hub | `isChildOf` hierarchy |
| OPC UA | Extractors ⚠ | Native to the automation stack | Via SiteWise ⚠ |
| AAS (IEC 63278) | ⚠ not found | SITRANS assetfox ([link](https://www.siemens.com/en-us/products/sitrans/assetfox/)) | ⚠ not found |
| RDF / OWL | Own property-graph model, not RDF | Graph Studio: W3C ontologies ([link](https://www.siemens.com/en-us/products/rapidminer/graph-studio/)) | Own graph model |
| Units | Unit catalog bound at container level ([Units](https://docs.cognite.com/dev/concepts/resource_types/units/units)) | Variable units on aspects | Component property units |

## 5. How does GenAI use the graph?

- **Cognite Atlas AI:** agents query the CDF knowledge graph through tools (query knowledge graph, document Q&A, time-series analysis). They require the Core Data Model and are also exposed through MCP. Cognite's guidance is to model assets as "contextual anchors" so agents can run multi-hop queries. Atlas AI is separately licensed ([About Atlas AI agents](https://docs.cognite.com/cdf/atlas_ai/concepts), [Agent tools](https://docs.cognite.com/cdf/atlas_ai/references/atlas_ai_agent_tools), [Optimizing data models for AI](https://docs.cognite.com/cdf/dm/dm_guides/dm_best_practices_ai_search/)).
- **Siemens Industrial Copilot:** built with Microsoft on Azure OpenAI. It generates and debugs automation code; a *Copilot for Operations* helps diagnose machine faults and can run on-premise ([Siemens press release](https://press.siemens.com/global/en/pressrelease/siemens-xcelerator-scaling-roll-out-generative-ai-siemens-industrial-copilot), [Siemens & Microsoft](https://press.siemens.com/global/en/pressrelease/siemens-and-microsoft-partner-drive-cross-industry-ai-adoption)). Its grounding comes from engineering and automation data more than from a plant knowledge graph ⚠.
- **AWS:** the TwinMaker knowledge graph is queried with PartiQL `MATCH` patterns, including variable-hop paths such as `(e1)-[]->{1,5}(e2)`, which an LLM agent can call as a tool ([Run knowledge-graph queries](https://docs.aws.amazon.com/iot-twinmaker/latest/guide/tm-knowledge-graph-use.html)).

## 6. Values vs metadata

All three keep **raw values out of the graph**:
- **Cognite:** a `CogniteTimeSeries` is a *node* in the graph (identified by space and externalId), while its **datapoints** go through the separate time-series API by `instance_id` ([Time series in data modeling](https://docs.cognite.com/cdf/dm/dm_guides/dm_integrate_with_time_series), [Datapoints](https://docs.cognite.com/api-reference/concepts/20230101/datapoints)).
- **Siemens:** the **IoT Time Series Service** stores records against an *asset + aspect*. Each record holds a timestamp, the aspect's variables and an optional `_qc` quality code. Writing the same timestamp again overwrites, with no versioning ([IoT Time Series](https://developer.siemens.com/insights-hub/docs/apis/iot-iottimeseries/api-iottimeseries-overview.html)).
- **AWS:** TwinMaker components point at external stores (such as SiteWise or Timestream) through data connectors; the graph holds the relationships ([Knowledge graph](https://docs.aws.amazon.com/iot-twinmaker/latest/guide/tm-knowledge-graph.html)).

**Query APIs:** Cognite offers GraphQL and REST over DMS; Siemens offers REST plus GraphQL in IIH Semantics; AWS offers PartiQL through `ExecuteQuery`.

## 7. Limits

| | Cognite | Siemens | AWS |
|---|---|---|---|
| Lock-in | Proprietary DMS schema (`cdf_cdm`); migration needs re-modelling | Strong tie to the Siemens automation stack | Tied to the AWS service mesh (SiteWise, Timestream) |
| Cost | Atlas AI is separately licensed ([link](https://docs.cognite.com/cdf/atlas_ai/concepts)) | Subscription | Knowledge graph needs the standard or tiered plan and is **charged per query** ([pricing](https://aws.amazon.com/iot-twinmaker/pricing/)) |
| Scale / ops | Container changes mean a new container, re-ingest and new view versions ([link](https://docs.cognite.com/cdf/dm/dm_concepts/dm_containers_views_datamodels)) | Time-series ingest throttled per asset/aspect (100 KB/s), up to 1 min sync after model changes ([link](https://developer.siemens.com/insights-hub/docs/apis/iot-iottimeseries/api-iottimeseries-overview.html)) | — |
| What still needs people | Confirming matches, writing regex rules, fixing tag misreads ([Troubleshooting](https://docs.cognite.com/cdf/integration/guides/contextualization/troubleshooting/)) | Building asset types and aspects by hand | Declaring every relationship |

## 8. Automotive use cases

| Vendor | Use case | Note |
|---|---|---|
| Siemens | **Schaeffler** (automotive supplier) uses Industrial Copilot to generate robot and automation code on the shop floor ([press release](https://press.siemens.com/global/en/pressrelease/ai-industry-schaeffler-and-siemens-bring-industrial-copilot-shopfloor)) | Vendor press release |
| AWS | **Volkswagen Digital Production Platform**: 43 sites connected, including a GenAI maintenance chatbot rolled out to 8 plants ([AWS case study](https://aws.amazon.com/solutions/case-studies/volkswagen-dpp-generativeai/), [VW press release](https://www.volkswagen-group.com/en/press-releases/more-efficient-smarter-more-resilient-volkswagen-group-collaborates-with-aws-to-help-transform-production-for-the-age-of-ai-19774)) | AWS industrial cloud in general; it does **not** state that TwinMaker is used |
| Cognite | ⚠ No named automotive OEM or Tier-1 case found. The closest is **Aarbakke** (machining, welding robots) ([case](https://www.cognite.com/en/customers/aarbakke)) and the [discrete manufacturing page](https://www.cognite.com/en/industries/discrete-manufacturing) | Stated as a gap |

## 9. Ideas borrowed for Parts C and D

From **Cognite** I borrow the core of the pipeline. Deterministic rules and engineer-confirmed matches are applied **before** the ML model; the model's score is gated by a threshold, and rejected pairs are remembered. Every link carries a `confidence` and a `status` (suggested / approved / rejected) exactly like `CogniteAnnotation`, and confirmed links are fed back as training labels (Cognite's `refit`). In Part D I mirror the **container/view split**: one storage schema (Neo4j node labels and properties) and several role-specific views (maintenance, quality, traceability) defined in the ontology file, with time-series *nodes* in the graph but datapoints in Parquet. From **Siemens** I take the type/aspect idea of reusable equipment *types* (a weld-robot type defines which signals it should have), which powers the "unit compatible with equipment type" feature. From **AWS** I take the variable-hop path pattern for the `feeds` traversal in query D4. All three agree that values stay outside the graph, which is why the graph holds only pointers.
