import json
from playwright.sync_api import sync_playwright

BASE = "https://sec2021.bihar.gov.in/claim-objection/"

def options(pg, sel_id):
    return pg.evaluate("""(id) => Array.from(document.getElementById(id).options).map(o=>({v:o.value,t:o.text.trim()}))""", sel_id)

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
    ctx = br.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.goto(BASE + "Result7.aspx", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_selector("#ctl00_ContentPlaceHolder1_ddl_Post")

    DIST = "#ctl00_ContentPlaceHolder1_ddlDistrict"
    BLOCK = "#ctl00_ContentPlaceHolder1_ddlBlock"

    # select post via onchange (auto postback)
    pg.select_option("#ctl00_ContentPlaceHolder1_ddl_Post", "3")
    pg.wait_for_load_state("networkidle", timeout=120000)
    print("after POST -> districts:", len(options(pg, DIST)))

    pg.select_option(DIST, "5")  # मधुबनी
    pg.wait_for_load_state("networkidle", timeout=120000)
    blocks = options(pg, BLOCK)
    print("BLOCKS:", json.dumps(blocks, ensure_ascii=False)[:600])

    if len(blocks) > 1:
        pg.select_option(BLOCK, blocks[1]["v"])
        pg.wait_for_load_state("networkidle", timeout=120000)
        blocks2 = options(pg, BLOCK)
        print("AFTER BLOCK SELECT -> block opts:", len(blocks2), "panchayat selects:",
              pg.evaluate("""()=>Array.from(document.querySelectorAll('select')).map(s=>s.id)"""))

        with pg.expect_navigation(wait_until="networkidle", timeout=300000):
            pg.click("#ctl00_ContentPlaceHolder1_btnFilter")
        res = pg.evaluate("""() => {
          const pm = document.querySelector('#printMe') || document.body;
          const tbls = Array.from(pm.querySelectorAll('table'));
          const info = tbls.map(t=>({rows:t.rows.length, head:Array.from(t.rows[0]?.cells||[]).map(c=>c.innerText.trim())}));
          const first = tbls.find(t=>t.rows.length>0);
          const sample = first ? Array.from(first.rows).slice(0,3).map(r=>Array.from(r.cells).map(c=>c.innerText.trim())) : [];
          const pag = Array.from(document.querySelectorAll("a,input[type=submit],input[type=image],span")).filter(e=>{
            const s=(e.id||'')+(e.name||'');return /RPDetails|Page|Next|Prev/i.test(s);}).map(e=>({tag:e.tagName,id:e.id,name:e.name,t:(e.innerText||e.value||'').slice(0,40)}));
          return {tables:info, sample, pag:pag.slice(0,15), textHead: pm.innerText.slice(0,400)};
        }""")
        print("RESULT:", json.dumps(res, ensure_ascii=False, indent=1)[:4000])
        open("probe_result.html","w",encoding="utf-8").write(pg.content())
    br.close()
