import json
from playwright.sync_api import sync_playwright

BASE = "https://sec2021.bihar.gov.in/claim-objection/"

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
    ctx = br.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.goto(BASE + "Result7.aspx", wait_until="domcontentloaded", timeout=90000)
    form = pg.locator("form")

    # 1. select post = 3 (मुखिया)
    form.select_option("#ctl00_ContentPlaceHolder1_ddl_Post", "3")
    with pg.expect_navigation(wait_until="networkidle", timeout=120000):
        pass  # postback may be auto via onchange? check
    print("POST selected; districts now:", len(pg.locator("#ctl00_ContentPlaceHolder1_ddlDistrict option").all()))

    # if no auto postback, force one by selecting district directly after __doPostBack? Try select district
    form.select_option("#ctl00_ContentPlaceHolder1_ddlDistrict", "5")  # मधुबनी
    try:
        pg.wait_for_load_state("networkidle", timeout=60000)
    except Exception as e:
        print("nav err", e)
    blocks = pg.evaluate("""() => Array.from(document.querySelectorAll('#ctl00_ContentPlaceHolder1_ddlBlock option')).map(o=>({v:o.value,t:o.text}))""")
    print("BLOCKS:", json.dumps(blocks, ensure_ascii=False))

    panch = pg.evaluate("""() => {
      const sels = Array.from(document.querySelectorAll('select')).map(s=>({id:s.id, n:s.options.length}));
      const tables = Array.from(document.querySelectorAll('table')).map(t=>t.id||t.className);
      return {sels, tables};
    }""")
    print("PAGE ELEMENTS:", json.dumps(panch, ensure_ascii=False))

    # 2. click Show without block? First pick a block
    if blocks and len(blocks) > 1:
        form.select_option("#ctl00_ContentPlaceHolder1_ddlBlock", blocks[1]["v"])
        pg.wait_for_timeout(1000)
        with pg.expect_navigation(wait_until="networkidle", timeout=180000):
            pg.click("#ctl00_ContentPlaceHolder1_btnFilter")
        res = pg.evaluate("""() => {
          const pm = document.querySelector('#printMe') || document.body;
          const tbl = pm.querySelector('table');
          const rows = tbl ? Array.from(tbl.rows).slice(0,4).map(r=>Array.from(r.cells).map(c=>c.innerText.trim())) : [];
          const pag = Array.from(document.querySelectorAll('a,input')).filter(e=>/page|next|prev/i.test((e.id||'')+(e.name||'')+(e.innerText||''))).map(e=>({id:e.id,name:e.name,t:(e.innerText||e.value||'').slice(0,30)}));
          return {rowCount: tbl?tbl.rows.length:0, sample: rows, pag: pag.slice(0,10), textLen: pm.innerText.length, head: pm.innerText.slice(0,300)};
        }""")
        print("RESULT:", json.dumps(res, ensure_ascii=False, indent=1))
        html = pg.content()
        open("probe_result.html","w",encoding="utf-8").write(html)
    br.close()
