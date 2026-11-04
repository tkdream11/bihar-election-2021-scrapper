import json, re
from playwright.sync_api import sync_playwright

BASE = "https://sec2021.bihar.gov.in/claim-objection/"
URL = BASE + "Result7.aspx"

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
    ctx = br.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.goto(URL, wait_until="networkidle", timeout=90000)
    html = pg.content()
    open("probe_form.html","w",encoding="utf-8").write(html)

    # list all inputs/selects/buttons
    els = pg.evaluate("""() => {
      const out = [];
      document.querySelectorAll('input,select,button').forEach(e=>{
        out.push({tag:e.tagName.toLowerCase(), id:e.id||null, name:e.name||null,
          type:e.type||null, value:(e.value||'').slice(0,60),
          opts: e.tagName==='SELECT' ? Array.from(e.options).slice(0,50).map(o=>({v:o.value,t:o.text})) : undefined});
      });
      return out;
    }""")
    print(json.dumps(els, ensure_ascii=False, indent=1)[:6000])
    br.close()
