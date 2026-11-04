# Part A link check – worksheet

**How to use it:** open each link and press **Ctrl + F** to search for the word in the "Search for" column.
Read the sentence around it and compare it with the claim. In the last column write one of:

- **OK**: the page says this.
- **Different: …**: the page says something else; write what, in a few words.
- **Gone**: 404, or the page moved; write the new link if you find it.

About 30–40 minutes for all 34 links. The ⚠ rows at the end aren't links; they're claims marked "not
found", where you just confirm that you also can't find them.

## Cognite (21 links)

| # | Link | Claim in our text | Search for | Result |
|---:|---|---|---|---|
| 1 | https://docs.cognite.com/cdf/dm/dm_concepts/dm_containers_views_datamodels | Containers = physical storage, views = logical schemas (can rename, combine, inherit with `implements`), data models group views, all scoped to a space. Changing a container means a new container + re-ingest | `implements`, `container` | |
| 2 | https://docs.cognite.com/cdf/dm/dm_reference/dm_core_data_model | Core Data Model `CogniteCore` in space `cdf_cdm`; CogniteAsset has parent, root, path; CogniteAnnotation has confidence + status Suggested / Approved / Rejected | `cdf_cdm`, `Suggested` | |
| 3 | https://docs.cognite.com/cdf/dm/dm_guides/dm_designing_scalable_models | Extend only the core views you populate; direct relations are the default relationship type | `direct relation` | |
| 4 | https://docs.cognite.com/cdf/integration/guides/contextualization/matching | Regex rules and confirmed matches are applied before model predictions; a match is used only above the threshold and if not in the rejected list | `threshold`, `rejected` | |
| 5 | https://docs.cognite.com/api-reference/concepts/20230101/entity-matching | Unsupervised model by default (weighted field similarity); supervised when `trueMatches` exist | `trueMatches`, `supervised` | |
| 6 | https://docs.cognite.com/cdf/integration/guides/contextualization/diagram_parsing | Diagram parsing finds tags, file references, symbols, connections; raster files give tags only | `raster`, `symbol` | |
| 7 | https://docs.cognite.com/cdf/integration/guides/contextualization/parse_diagrams | Tag detection is GA, full parsing is in preview | `preview` | |
| 8 | https://docs.cognite.com/cdf/integration/guides/contextualization/match_entities/ | Entity matching via pipelines, quick match, manual confirmation | `quick match` | |
| 9 | https://cognite-sdk-python.readthedocs-hosted.com/en/latest/contextualization.html | SDK `predict` takes `score_threshold`; `refit` retrains with new true matches | `score_threshold`, `refit` | |
| 10 | https://docs.cognite.com/cdf/integration/guides/contextualization/interactive_diagrams | Suggested links orange, verified blue; bulk approve / reject | `orange`, `approve` | |
| 11 | https://docs.cognite.com/cdf/dm/dm_guides/dm_cdm_build_asset_hierarchy | Building an asset hierarchy with CogniteAsset parent/path | `parent` | |
| 12 | https://docs.cognite.com/dev/concepts/resource_types/units/units | Unit catalog, units bound at container level | `unit`, `container` | |
| 13 | https://docs.cognite.com/cdf/atlas_ai/concepts | Atlas AI agents use tools; need the Core Data Model; separately licensed | `license`, `agent` | |
| 14 | https://docs.cognite.com/cdf/atlas_ai/references/atlas_ai_agent_tools | Tools such as query knowledge graph, document Q&A, time-series analysis | `knowledge graph` | |
| 15 | https://docs.cognite.com/cdf/dm/dm_guides/dm_best_practices_ai_search/ | Model assets as "contextual anchors" so agents can do multi-hop queries | `anchor` | |
| 16 | https://docs.cognite.com/cdf/dm/dm_guides/dm_integrate_with_time_series | CogniteTimeSeries is a node; datapoints go through the time-series API by `instance_id` | `instance_id`, `datapoints` | |
| 17 | https://docs.cognite.com/api-reference/concepts/20230101/datapoints | Datapoints API (values outside the graph) | `datapoints` | |
| 18 | https://docs.cognite.com/cdf/integration/guides/contextualization/troubleshooting/ | People still confirm matches, write regex rules, fix tag misreads | `regex` | |
| 19 | https://www.cognite.com/en/customers/aarbakke | Aarbakke: machining, welding robots (closest case to automotive) | `weld`, `robot` | |
| 20 | https://www.cognite.com/en/industries/discrete-manufacturing | Discrete manufacturing page (no named car maker found) | `automotive` | |
| 21 | MCP mention for Atlas AI (link 13 or 14) | Atlas AI agents are also exposed through MCP | `MCP` | |

## Siemens (9 links)

| # | Link | Claim | Search for | Result |
|---:|---|---|---|---|
| 22 | https://developer.siemens.com/insights-hub/docs/apis/advanced-assetmanagement/api-assetmanagement-overview.html | Asset types built from variables + aspects, inherited from the parent type; static variables can't receive time series | `aspect`, `static` | |
| 23 | https://developer.siemens.com/industrial-information-hub/overview.html | IIH Semantics: GraphQL API backed by a knowledge graph | `GraphQL`, `knowledge graph` | |
| 24 | https://www.siemens.com/en-us/products/rapidminer/graph-studio/ | Graph Studio built on W3C ontologies; links PLM/ERP/MES without copying | `W3C`, `ontolog` | |
| 25 | https://www.siemens.com/en-us/solutions/data-analytics-artificial-intelligence/knowledge-graphs/ | Siemens knowledge graph offering | `knowledge graph` | |
| 26 | https://www.siemens.com/en-us/products/sitrans/assetfox/ | SITRANS assetfox: AAS repository, registry, AASX server | `AAS`, `registry` | |
| 27 | https://developer.siemens.com/insights-hub/docs/apis/iot-iottimeseries/api-iottimeseries-overview.html | Records per asset + aspect, optional `_qc`, same timestamp overwrites, 100 KB/s per asset/aspect, up to 1 min sync | `_qc`, `100`, `overwrit` | |
| 28 | https://press.siemens.com/global/en/pressrelease/siemens-xcelerator-scaling-roll-out-generative-ai-siemens-industrial-copilot | Industrial Copilot generates/debugs automation code; operations copilot, can run on-premise | `on-prem`, `code` | |
| 29 | https://press.siemens.com/global/en/pressrelease/siemens-and-microsoft-partner-drive-cross-industry-ai-adoption | Built with Microsoft on Azure OpenAI | `Azure OpenAI` | |
| 30 | https://press.siemens.com/global/en/pressrelease/ai-industry-schaeffler-and-siemens-bring-industrial-copilot-shopfloor | Schaeffler uses Industrial Copilot for robot/automation code on the shop floor | `Schaeffler`, `robot` | |

## AWS (5 links)

| # | Link | Claim | Search for | Result |
|---:|---|---|---|---|
| 31 | https://docs.aws.amazon.com/iot-twinmaker/latest/guide/tm-knowledge-graph.html | Entities + components; relationship properties become edges; parentEntityId gives `isChildOf` | `isChildOf` | |
| 32 | https://docs.aws.amazon.com/iot-twinmaker/latest/guide/tm-knowledge-graph-use.html | PartiQL `MATCH`, variable-hop paths like `{1,5}` | `MATCH`, `{1,5}` | |
| 33 | https://aws.amazon.com/iot-twinmaker/pricing/ | Knowledge graph needs standard / tiered plan, charged per query | `query`, `knowledge graph` | |
| 34 | https://aws.amazon.com/solutions/case-studies/volkswagen-dpp-generativeai/ | VW Digital Production Platform: 43 sites; GenAI maintenance chatbot in 8 plants; TwinMaker not named | `43`, `8 plants`, `TwinMaker` | |
| 35 | https://www.volkswagen-group.com/en/press-releases/more-efficient-smarter-more-resilient-volkswagen-group-collaborates-with-aws-to-help-transform-production-for-the-age-of-ai-19774 | VW press release on the same collaboration | `AWS` | |

## ⚠ "Not found" claims – confirm you can't find them either (5 minutes)

| Claim | Where to look | Result |
|---|---|---|
| No AAS support documented *inside* Insights Hub | search "Insights Hub Asset Administration Shell" | |
| No ML entity matcher documented for Siemens or AWS | search "Siemens entity matching", "TwinMaker entity matching" | |
| No named car maker in a Cognite case study | cognite.com/customers, filter industry | |
| OPC UA via Cognite extractors / via SiteWise | search "Cognite OPC UA extractor", "SiteWise OPC UA" | |
| Siemens Copilot grounding is engineering data, not a plant graph | link 28 | |

If you *do* find a link for a ⚠ claim, that's a bonus: paste it here and the ⚠ can go.

## When you're done

Paste me the rows that are **not OK** (just the numbers and what you wrote). I'll fix the text in
`docs/part_a_research.md` and `report/REPORT.md`, remove the yellow source-status note, and rebuild the PDF.
If everything is OK, just say "all OK".
