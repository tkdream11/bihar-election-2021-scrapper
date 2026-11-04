import json, sys
from playwright.sync_api import sync_playwright

BASE = "https://sec2021.bihar.gov.in/claim-objection/"
POST_ID = "ctl00_ContentPlaceHolder1_ddl_Post"
DIST_ID = "ctl00_ContentPlaceHolder1_ddlDistrict"
BLOCK_ID = "ctl00_ContentPlaceHolder1_ddlBlock"
PANCH_ID = "ctl00_ContentPlaceHolder1_ddlPanchayat"

def opts(pg, eid):
    return pg.evaluate("""(id)=>{const e=document.getElementById(id); if(!e) return null; return Array.from(e.options).map(o=>({v:o.value,t:o.text.trim()}));}""", eid)

def clear_swal(pg):
    try:
        pg.evaluate("""()=>{document.querySelectorAll('.swal-overlay,.modal-backdrop').forEach(e=>e.remove()); if(window.jQuery) jQuery.ajaxAbort && 0;}""")
    except Exception: pass

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
    ctx = br.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.goto(BASE + "Result7.aspx", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_selector("#"+POST_ID, timeout=60000)
    try: pg.wait_for_load_state("networkidle", timeout=120000)
    except Exception: pass

    pg.select_option("#"+POST_ID, "3")
    pg.dispatch_event("#"+POST_ID, "change")
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception: pass

    # district -> Show -> blocks
    pg.evaluate("""()=>{document.getElementById('ctl00_ContentPlaceHolder1_ddlDistrict').value='5';}""")
    with pg.expect_navigation(wait_until="load", timeout=300000):
        pg.click("#ctl00_ContentPlaceHolder1_btnFilter")
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception: pass
    b = opts(pg, BLOCK_ID)
    print("blocks:", [x["t"] for x in (b or [])])

    # block -> Show -> panchayats
    clear_swal(pg)
    pg.evaluate("""(bv)=>{document.getElementById('ctl00_ContentPlaceHolder1_ddlBlock').value=bv;}""", b[1]["v"])
    with pg.expect_navigation(wait_until="load", timeout=300000):
        pg.click("#ctl00_ContentPlaceHolder1_btnFilter", force=True)
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception: pass
    p = opts(pg, PANCH_ID)
    print("panchayats:", json.dumps(p, ensure_ascii=False)[:800] if p is not None else None)

    if p and len(p)>1:
        clear_swal(pg)
        target = next((o for o in p if o["v"] not in ("0","-1")), p[1])
        pg.evaluate("""(pv)=>{const el=document.getElementById('ctl00_ContentPlaceHolder1_ddlPanchayat'); if(el) el.value=pv;}""", target["v"])
        with pg.expect_navigation(wait_until="load", timeout=300000):
            pg.click("#ctl00_ContentPlaceHolder1_btnFilter", force=True)
        try: pg.wait_for_load_state("networkidle", timeout=180000)
        except Exception: pass
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
