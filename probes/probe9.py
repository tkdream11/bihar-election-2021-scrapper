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

    # post 3 via dispatch change (this worked before: districts stayed 38)
    pg.select_option("#"+POST_ID, "3")
    pg.dispatch_event("#"+POST_ID, "change")
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception as e: print("warn:", str(e)[:50], file=sys.stderr)
    print("districts:", len(opts(pg, DIST_ID) or []))

    # District: click select to focus, then press key 'अ'? Better: use page.select_option then click elsewhere & blur? Try keyboard selection after focusing.
    el = pg.locator("#"+DIST_ID)
    el.click()                      # opens native dropdown in headed; in headless focuses
    pg.keyboard.press("Tab")        # ? not reliable
    # Instead: set value and fire onchange handler directly through the element's attribute string
    pg.evaluate("""()=>{
      const s=document.getElementById('%s');
      s.selectedIndex = Array.from(s.options).findIndex(o=>o.value==='5');
      const oc = s.getAttribute('onchange');
      eval(oc.replace(/\\\\\\'/g,"'"));
    }""" % DIST_ID)
    try: pg.wait_for_load_state("networkidle", timeout=180000)
    except Exception as e: print("warn2:", str(e)[:50], file=sys.stderr)
    b = opts(pg, BLOCK_ID)
    print("blocks:", json.dumps(b, ensure_ascii=False)[:600] if b is not None else None)
    br.close()
