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
    postbacks = []
    def on_req(req):
        if req.method == "POST":
            pd = req.post_data or ""
            et = ""
            for line in pd.split("&"):
                if line.startswith("__EVENTTARGET="):
                    et = line.split("=",1)[1]
            postbacks.append(et)
    pg.on("request", on_req)

    pg.goto(BASE + "Result7.aspx", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_selector("#"+POST_ID, timeout=60000)
    try: pg.wait_for_load_state("networkidle", timeout=120000)
    except Exception: pass

    pg.select_option("#"+POST_ID, "3")
    pg.dispatch_event("#"+POST_ID, "change")
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception as e: print("warn:", str(e)[:50], file=sys.stderr)
    print("postbacks after POST step:", postbacks)
    print("districts:", len(opts(pg, DIST_ID) or []))

    # now user-style interaction for district
    sel = pg.locator("#"+DIST_ID)
    sel.scroll_into_view_if_needed()
    sel.click(timeout=10000)
    pg.wait_for_timeout(400)
    idx = pg.evaluate("""()=>Array.from(document.getElementById('ctl00_ContentPlaceHolder1_ddlDistrict').options).findIndex(o=>o.value==='5')""")
    for _ in range(idx):
        pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Tab")   # commit change (blur fires change since value differs)
    print("waiting for district postback...")
    try: pg.wait_for_load_state("networkidle", timeout=240000)
    except Exception as e: print("warn2:", str(e)[:50], file=sys.stderr)
    print("postbacks total:", postbacks)
    b = opts(pg, BLOCK_ID)
    print("blocks:", json.dumps(b, ensure_ascii=False)[:600] if b is not None else None)
    hf = pg.evaluate("""()=>({d:document.querySelector('[id$=hfDist]').value,b:document.querySelector('[id$=hfBlock]').value})""")
    print("HF:", hf)
    br.close()
