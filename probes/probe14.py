import json, sys
from playwright.sync_api import sync_playwright

BASE = "https://sec2021.bihar.gov.in/claim-objection/"
POST_ID = "ctl00_ContentPlaceHolder1_ddl_Post"
DIST_ID = "ctl00_ContentPlaceHolder1_ddlDistrict"
BLOCK_ID = "ctl00_ContentPlaceHolder1_ddlBlock"

def opts(pg, eid):
    return pg.evaluate("""(id)=>{const e=document.getElementById(id); if(!e) return null; return Array.from(e.options).map(o=>({v:o.value,t:o.text.trim()}));}""", eid)

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
    ctx = br.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.goto(BASE + "Result7.aspx", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_selector("#"+POST_ID, timeout=60000)
    try: pg.wait_for_load_state("networkidle", timeout=120000)
    except Exception: pass

    # post 3 via change dispatch
    pg.select_option("#"+POST_ID, "3")
    pg.dispatch_event("#"+POST_ID, "change")
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception as e: print("warn:", str(e)[:50], file=sys.stderr)

    # district silently + Show -> loads blocks (verified pattern)
    pg.evaluate("""()=>{document.getElementById('ctl00_ContentPlaceHolder1_ddlDistrict').value='5';}""")
    with pg.expect_navigation(wait_until="load", timeout=300000):
        pg.click("#ctl00_ContentPlaceHolder1_btnFilter")
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception: pass
    b = opts(pg, BLOCK_ID)
    print("blocks:", json.dumps(b, ensure_ascii=False))

    if b and len(b)>1:
        # block silently + Show
        pg.evaluate("""(bv)=>{document.getElementById('ctl00_ContentPlaceHolder1_ddlBlock').value=bv;}""", b[1]["v"])
        sels_before = pg.evaluate("""()=>Array.from(document.querySelectorAll('select')).map(s=>s.id)""")
        with pg.expect_navigation(wait_until="load", timeout=300000):
            pg.click("#ctl00_ContentPlaceHolder1_btnFilter")
        try: pg.wait_for_load_state("networkidle", timeout=180000)
        except Exception: pass
        sels_after = pg.evaluate("""()=>Array.from(document.querySelectorAll('select')).map(s=>({id:s.id,n:s.options.length}))""")
        print("SELECTS AFTER BLOCK+SHOW:", json.dumps(sels_after, ensure_ascii=False))
        res = pg.evaluate("""() => {
          const pm = document.querySelector('#printMe') || document.body;
          const tbls = Array.from(pm.querySelectorAll('table'));
          const info = tbls.map(t=>({rows:t.rows.length, head:Array.from((t.rows[0]&&t.rows[0].cells)||[]).map(c=>c.innerText.trim())}));
          const first = tbls.find(t=>t.rows.length>1);
          const sample = first ? Array.from(first.rows).slice(0,4).map(r=>Array.from(r.cells).map(c=>c.innerText.trim())) : [];
          const pag = Array.from(document.querySelectorAll('a,input,span')).filter(e=>/RPDetails|Page/i.test((e.id||'')+(e.name||''))).map(e=>({tag:e.tagName,id:e.id,name:e.name,t:(e.innerText||e.value||'').slice(0,40)}));
          return {tables:info.slice(0,6), sample, pagCount:pag.length, pag:pag.slice(0,14), textHead: pm.innerText.slice(0,700)};
        }""")
        print("RESULT:", json.dumps(res, ensure_ascii=False, indent=1)[:6000])
        open("probe_result.html","w",encoding="utf-8").write(pg.content())
    br.close()
