import json, sys
from playwright.sync_api import sync_playwright

BASE = "https://sec2021.bihar.gov.in/claim-objection/"
POST_ID = "ctl00_ContentPlaceHolder1_ddl_Post"
DIST_ID = "ctl00_ContentPlaceHolder1_ddlDistrict"
BLOCK_ID = "ctl00_ContentPlaceHolder1_ddlBlock"

def opts(pg, eid):
    return pg.evaluate("""(id)=>{const e=document.getElementById(id); if(!e) return null; return Array.from(e.options).map(o=>({v:o.value,t:o.text.trim()}));}""", eid)

def wait_ready(pg, t=240000):
    try: pg.wait_for_load_state("networkidle", timeout=t)
    except Exception as e: print("warn idle:", str(e)[:60], file=sys.stderr)

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
    ctx = br.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.goto(BASE + "Result7.aspx", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_selector("#"+POST_ID, timeout=60000)
    wait_ready(pg)

    # Post 3 (मुखिया) via real change event -> full page postback
    pg.select_option("#"+POST_ID, "3")
    pg.dispatch_event("#"+POST_ID, "change")
    try:
        pg.wait_for_navigation(timeout=240000)
    except Exception as e:
        print("nav warn:", str(e)[:60], file=sys.stderr)
    wait_ready(pg)
    print("districts:", len(opts(pg, DIST_ID) or []))

    # District 5 (मधुबनी) - set value WITHOUT onchange firing, then force submit manually
    pg.evaluate("""()=>{document.getElementById('%s').value='5';}""" % DIST_ID)
    pg.evaluate("""()=>{__doPostBack('ctl00$ContentPlaceHolder1$ddlDistrict','');}""")
    try:
        pg.wait_for_navigation(timeout=240000)
    except Exception as e:
        print("nav warn2:", str(e)[:60], file=sys.stderr)
    wait_ready(pg)
    b = opts(pg, BLOCK_ID)
    print("blocks:", json.dumps(b, ensure_ascii=False)[:700] if b is not None else None)

    if b and len(b) > 1:
        # Block select + Show click
        pg.evaluate("""(v)=>{document.getElementById('%s').value=v;}""" % BLOCK_ID, b[1]["v"])
        with pg.expect_navigation(wait_until="load", timeout=300000):
            pg.click("#ctl00_ContentPlaceHolder1_btnFilter")
        wait_ready(pg, 180000)
        res = pg.evaluate("""() => {
          const pm = document.querySelector('#printMe') || document.body;
          const tbls = Array.from(pm.querySelectorAll('table'));
          const info = tbls.map(t=>({rows:t.rows.length, head:Array.from((t.rows[0]&&t.rows[0].cells)||[]).map(c=>c.innerText.trim())}));
          const first = tbls.find(t=>t.rows.length>1);
          const sample = first ? Array.from(first.rows).slice(0,3).map(r=>Array.from(r.cells).map(c=>c.innerText.trim())) : [];
          const pag = Array.from(document.querySelectorAll('a,input,span')).filter(e=>/RPDetails|Page/i.test((e.id||'')+(e.name||''))).map(e=>({tag:e.tagName,id:e.id,name:e.name,t:(e.innerText||e.value||'').slice(0,40)}));
          return {tables:info.slice(0,6), sample, pagCount:pag.length, pag:pag.slice(0,14), textHead: pm.innerText.slice(0,600)};
        }""")
        print("RESULT:", json.dumps(res, ensure_ascii=False, indent=1)[:6000])
        open("probe_result.html","w",encoding="utf-8").write(pg.content())
    br.close()
