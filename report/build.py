"""Build report/REPORT.pdf from report/REPORT.md (pandoc -> HTML -> Chromium print via Playwright for Node).

    python report/build.py

Needs pandoc and Playwright's Chromium. The Markdown is the source; the PDF is what gets submitted.
"""
import subprocess
from pathlib import Path

import re

HERE = Path(__file__).resolve().parent
html = HERE / "REPORT.html"
QUERIES = HERE.parent / "reports" / "12_graph_queries.md"
MAX_ROWS = 3
MAX_NOTES = 3


def query_appendix() -> str:
    """Appendix A from the real query report: each required query (D1-D7) with its Cypher and output,
    long tables cut to MAX_ROWS rows. Regenerated on every build, so it always matches the graph."""
    text = QUERIES.read_text(encoding="utf-8")
    out = ["", "# Appendix A – The seven required queries: Cypher and real output", "",
           "Generated from `reports/12_graph_queries.md` (produced by `python -m ddn.queries` against the "
           f"loaded graph). Tables are cut to {MAX_ROWS} rows; the full output is in that file.", "",
           ""]
    for sec in re.split(r"(?m)^## ", text)[1:]:
        title, body = sec.split("\n", 1)
        if not re.match(r"D[1-7]\.", title):                    # D3b, D6b, E1 stay in the full report
            continue
        out += [f"**{title.strip()}**", ""]
        rows, kept, notes = 0, [], 0
        for line in body.strip().splitlines():
            if line.startswith("- "):                             # notes under a query: keep the first 3
                notes += 1
                if notes > MAX_NOTES:
                    continue
            if line.startswith("|") and not line.startswith("|---"):
                rows += 1
                if rows > MAX_ROWS + 1:                          # +1 = header row
                    continue
            elif rows > MAX_ROWS + 1 and not line.startswith("|"):
                kept.append(f"| … {rows - MAX_ROWS - 1} more rows |")
                rows = 0
            elif not line.startswith("|"):
                rows = 0
            kept.append(line)
        out += kept + [""]
    return "\n".join(out)


GRAPHRAG = HERE.parent / "reports" / "14_graphrag.md"
ANSWER_CHARS = 110


def graphrag_appendix() -> str:
    """Appendix B from the real GraphRAG report: the 10 evaluation questions and held-out round 2, with expected
    and actual answers (answers cut to ANSWER_CHARS characters; full text and Cypher in reports/14)."""
    text = GRAPHRAG.read_text(encoding="utf-8")
    mode = re.search(r"\*\*Mode: ([^*]+)\.\*\*", text)
    out = ["", "# Appendix B – GraphRAG test questions: expected vs actual answers", "",
           f"From `reports/14_graphrag.md` (mode: {mode.group(1) if mode else 'unknown'}). Answers are cut to "
           f"{ANSWER_CHARS} characters; the full answers and the Cypher behind each one are in that file. "
           "\"Pass\" is the automatic check; see section 4 for the one held-out answer that fails on manual review.", ""]
    for sec, title in [(text.split("## Held-out round 2")[0], "Evaluation set (10, incl. 2 \"I don't know\")"),
                       ("## Held-out round 2" + text.split("## Held-out round 2")[1].split("## Held-out round 1")[0],
                        "Held-out round 2 (unseen)")]:
        out += [f"**{title}**", ""]
        for line in sec.splitlines():
            if line.startswith("| ") and not line.startswith("| # |"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) == 5:
                    ans = cells[3] if len(cells[3]) <= ANSWER_CHARS else cells[3][:ANSWER_CHARS].rsplit(" ", 1)[0] + " …"
                    line = f"| {cells[0]} | {cells[1]} | {cells[2]} | {ans} | {cells[4]} |"
            if line.startswith("|"):
                out.append(line)
        out.append("")
    return "\n".join(out)


src = HERE / "REPORT.full.md"
src.write_text((HERE / "REPORT.md").read_text(encoding="utf-8") + query_appendix() + graphrag_appendix(),
               encoding="utf-8")
subprocess.run(["pandoc", str(src), "-o", str(html), "--standalone", "--embed-resources",
                "--css", str(HERE / "report.css"), "--resource-path", str(HERE), "--metadata", "lang=en"],
               check=True, cwd=HERE)
FOOTER = ('<div style="font-size:7pt;color:#777;width:100%;text-align:center;">Plant DDN-01 contextualization '
          '&amp; knowledge graph – page <span class="pageNumber"></span> of <span class="totalPages"></span></div>')
JS = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('{html.as_uri()}');
  await p.pdf({{ path: '{HERE / "REPORT.pdf"}', format: 'A4', printBackground: true, displayHeaderFooter: true,
    headerTemplate: '<span></span>', footerTemplate: '{FOOTER}',
    margin: {{ top: '15mm', bottom: '16mm', left: '15mm', right: '15mm' }} }});
  await b.close();
}})();
"""
subprocess.run(["node", "-e", JS], check=True)       # Playwright for Node (pre-installed with Chromium)
html.unlink()
src.unlink()
print("report/REPORT.pdf")
