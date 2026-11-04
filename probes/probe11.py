import json, sys, re
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
    reqs = []
    def on_resp(r):
        if "Result7" in r.url or ".aspx" in r.url:
            try: body = r.text()[:400]
            except Exception: body = ""
            reqs.append({"url": r.url[-60:], "status": r.status, "body_head": body.replace("\n"," ")[:200]})
    pg.on("response", on_resp)

    pg.goto(BASE + "Result7.aspx", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_selector("#"+POST_ID, timeout=60000)
    try: pg.wait_for_load_state("networkidle", timeout=120000)
    except Exception: pass

    # post 3 via dispatch change (worked before)
    pg.select_option("#"+POST_ID, "3")
    pg.dispatch_event("#"+POST_ID, "change")
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception as e: print("warn:", str(e)[:50], file=sys.stderr)
    print("districts:", len(opts(pg, DIST_ID) or []))

    # district via select_option + dispatch change (same method that WORKED for post!)
    pg.select_option("#"+DIST_ID, "5")
    pg.dispatch_event("#"+DIST_ID, "change")
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception as e: print("warn2:", str(e)[:50], file=sys.stderr)
    b = opts(pg, BLOCK_ID)
    print("blocks:", json.dumps(b, ensure_ascii=False)[:400] if b is not None else None)
    hf = pg.evaluate("""()=>({d:document.querySelector('[id$=hfDist]').value,b:document.querySelector('[id$=hfBlock]').value})""")
    print("HF after district:", hf)
    print("RESPONSES:")
    for r in reqs[-6:]:
        print(json.dumps(r, ensure_ascii=False))
    br.close()
