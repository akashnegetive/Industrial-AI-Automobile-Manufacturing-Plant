"""Build docs/demo_video/DEMO_VIDEO_GUIDE.pdf:  python docs/demo_video/build.py  (pandoc + Node Playwright)."""
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
html = HERE / "guide.html"
subprocess.run(["pandoc", str(HERE / "DEMO_VIDEO_GUIDE.md"), "-o", str(html), "--standalone", "--embed-resources",
                "--css", str(HERE / "guide.css"), "--metadata", "lang=en"], check=True, cwd=HERE)
FOOT = ('<div style="font-size:8pt;color:#777;width:100%;text-align:center;">Demo video guide – page '
        '<span class="pageNumber"></span> of <span class="totalPages"></span></div>')
JS = f"""
const {{ chromium }} = require('playwright');
(async () => {{
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('{html.as_uri()}');
  await p.pdf({{ path: '{HERE / "DEMO_VIDEO_GUIDE.pdf"}', format: 'A4', printBackground: true, displayHeaderFooter: true,
    headerTemplate: '<span></span>', footerTemplate: '{FOOT}',
    margin: {{ top: '14mm', bottom: '15mm', left: '15mm', right: '15mm' }} }});
  await b.close();
}})();
"""
subprocess.run(["node", "-e", JS], check=True)
html.unlink()
print(HERE / "DEMO_VIDEO_GUIDE.pdf")
