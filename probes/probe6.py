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

    # post 3 -> districts
    pg.select_option("#"+POST_ID, "3")
    pg.dispatch_event("#"+POST_ID, "change")
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception as e: print("warn:", str(e)[:60], file=sys.stderr)
    print("districts:", len(opts(pg, DIST_ID) or []))

    # click district option like a user (dropdown overlay)
    pg.click("#"+DIST_ID)
    pg.wait_for_timeout(500)
    pg.select_option("#"+DIST_ID, "5")   # sets value
    pg.keyboard.press("Enter")           # commit native select on some platforms
    pg.wait_for_timeout(1000)
    pg.evaluate("""()=>{const s=document.getElementById('%s'); s.dispatchEvent(new Event('change',{bubbles:true}));}""" % DIST_ID)
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception as e: print("warn2:", str(e)[:60], file=sys.stderr)
    b = opts(pg, BLOCK_ID)
    print("blocks:", json.dumps(b, ensure_ascii=False)[:500] if b is not None else None)

    # Fallback: direct __doPostBack with explicit param format
    if not b or len(b) <= 1:
        print("trying __doPostBack direct...")
        pg.evaluate("""()=>{__doPostBack('ctl00$ContentPlaceHolder1$ddlDistrict','')}""")
        try: pg.wait_for_load_state("networkidle", timeout=180000)
        except Exception as e: print("warn3:", str(e)[:60], file=sys.stderr)
        b = opts(pg, BLOCK_ID)
        print("blocks after dopostback:", json.dumps(b, ensure_ascii=False)[:500] if b is not None else None)
    br.close()
