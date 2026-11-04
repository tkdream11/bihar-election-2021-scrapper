#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bihar Panchayat Election 2021 – Claim/Objection Result Scraper (Playwright)
============================================================================
Source : https://sec2021.bihar.gov.in/claim-objection/Result7.aspx

The site is an ASP.NET WebForms app. Cascading dropdowns:
    Post (पद) -> District (जिला) -> Block/PR (प्रखंड) -> Panchayat (पंचायत)

Data is saved as JSON mirroring the filter hierarchy:

    data/
      <post-slug>/                 e.g. sarpanch/
        <district-slug>/           e.g. madhubani/
          <block-slug>/            e.g. madhwapur/
            <panchayat-slug>.json  e.g. uttara.json
      metadata.json                master index of everything scraped

Each panchayat JSON contains the candidate rows exactly as shown on the site
(जिला / प्रखंड / पंचायत / पद / प्रत्याशी का नाम / कुल प्राप्त मत).

Usage examples
--------------
  # crawl EVERYTHING for Sarpanch post (all districts/blocks/panchayats):
  python scraper.py --post sarpanch

  # only one district:
  python scraper.py --post mukhiya --district मधुबनी

  # one block inside a district:
  python scraper.py --post pradhan --district समस्तीपुर --block बरौनी

  # single panchayat (fastest, exact leaf):
  python scraper.py --post sarpanch --district 5 --block 1 --panchayat 050010008

  # list available posts / districts / blocks / panchayats (no scraping):
  python scraper.py --list posts
  python scraper.py --list districts --post sarpanch
  python scraper.py --list blocks   --post sarpanch --district मधुबनी
  python scraper.py --list panchayats --post sarpanch --district मधुबनी --block मधवापुर

Filters accept either the raw option VALUE (e.g. "5"), the Hindi label
(e.g. "मधुबनी") or an English slug/name (e.g. "madhubani") when known.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

BASE_URL = "https://sec2021.bihar.gov.in/claim-objection/Result7.aspx"

POST_ID = "ctl00_ContentPlaceHolder1_ddl_Post"
DIST_ID = "ctl00_ContentPlaceHolder1_ddlDistrict"
BLOCK_ID = "ctl00_ContentPlaceHolder1_ddlBlock"
PANCH_ID = "ctl00_ContentPlaceHolder1_ddlPanchayat"
SHOW_BTN = "ctl00_ContentPlaceHolder1_btnFilter"

SELECTORS = {
    "post": "#" + POST_ID,
    "district": "#" + DIST_ID,
    "block": "#" + BLOCK_ID,
    "panchayat": "#" + PANCH_ID,
}

NAV_TIMEOUT = 300_000       # ms – these pages can be slow
IDLE_TIMEOUT = 120_000      # ms
RETRIES = 3                 # per navigation action


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def slugify(text):
    """Make a filesystem-safe folder/file name from a Hindi/English label."""
    if not text:
        return "unknown"
    t = unicodedata.normalize("NFKC", str(text)).strip()
    # Devanagari labels: keep them readable but strip path-hostile chars
    t = re.sub(r"[\\/:*?\"<>|]+", "-", t)
    t = re.sub(r"\s+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_-. ")
    return t or "unknown"


def normalize(s):
    """Comparison helper: NFKC + casefold + collapse spaces."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s))).strip().casefold()


class Result7Scraper:
    def __init__(self, headless=True, out_dir="data"):
        self.headless = headless
        self.out_dir = out_dir
        self.pw = None
        self.br = None
        self.ctx = None
        self.pg = None
        self.stats = {"scraped": 0, "empty": 0, "failed": [], "started": None}

    # ---------------- low level helpers ----------------

    def start(self):
        self.pw = sync_playwright().start()
        self.br = self.pw.chromium.launch(
            headless=self.headless, args=["--ignore-certificate-errors"]
        )
        self.ctx = self.br.new_context(ignore_https_errors=True)
        self.pg = self.ctx.new_page()
        self.pg.set_default_timeout(NAV_TIMEOUT)

    def stop(self):
        for closer in (getattr(self, "br", None), getattr(self, "pw", None)):
            try:
                if closer:
                    closer.close() if hasattr(closer, "close") else closer.stop()
            except Exception:
                pass

    def _clear_blockers(self):
        """Remove sweetalert overlays that intercept clicks."""
        try:
            self.pg.evaluate(
                "()=>{document.querySelectorAll('.swal-overlay,.modal-backdrop')"
                ".forEach(e=>e.remove());}"
            )
        except Exception:
            pass

    def _wait_idle(self):
        try:
            self.pg.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT)
        except Exception:
            pass

    def _goto_fresh(self):
        for attempt in range(1, RETRIES + 1):
            try:
                self.pg.goto(BASE_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                self.pg.wait_for_selector(SELECTORS["post"], timeout=60_000)
                self._wait_idle()
                # server occasionally returns the form with dropdowns still empty;
                # reload until the post options are actually populated.
                if self._options("post"):
                    return
                log("  ~ page came with empty dropdowns, reloading…")
            except Exception as e:
                log(f"  ! page load failed ({attempt}/{RETRIES}): {str(e)[:80]}")
            time.sleep(2 * attempt)
        raise RuntimeError("Could not load Result7.aspx with populated dropdowns")

    def _options(self, key):
        sel = SELECTORS[key]
        return self.pg.evaluate(
            """(id)=>{const e=document.querySelector(id);
               if(!e) return null;
               return Array.from(e.options)
                 .filter(o=>o.value && o.value!=='-1' && o.text.trim().toLowerCase()!=='select')
                 .map(o=>({v:o.value,t:o.text.trim()}));}""",
            sel,
        )

    def _set_value(self, key, value):
        self.pg.evaluate(
            "(a)=>{const el=document.querySelector(a.s); if(el) el.value=a.v;}",
            {"s": SELECTORS[key], "v": str(value)},
        )

    def _click_show(self, expect_nav=True):
        """Click 'Show' and wait for the full-page postback to settle."""
        self._clear_blockers()
        try:
            if expect_nav:
                with self.pg.expect_navigation(wait_until="load", timeout=NAV_TIMEOUT):
                    self.pg.click("#" + SHOW_BTN, force=True)
            else:
                self.pg.click("#" + SHOW_BTN, force=True)
        except Exception:
            # navigation may have completed before expect caught it
            pass
        self._wait_idle()
        self._clear_blockers()

    def _select_post(self, value):
        """Post dropdown has AutoPostBack via onchange -> dispatch change."""
        self.pg.select_option(SELECTORS["post"], str(value))
        self.pg.dispatch_event(SELECTORS["post"], "change")
        self._wait_idle()

    # ---------------- filtering helpers ----------------

    @staticmethod
    def match_option(options, needle):
        """Return the option whose value/label/slug matches `needle`."""
        if needle is None:
            return None
        n = normalize(needle)
        for o in options:
            if normalize(o["v"]) == n or normalize(o["t"]) == n:
                return o
            if slugify(o["t"]).casefold() == n.replace(" ", "_").casefold():
                return o
        # loose contains match on label
        for o in options:
            if n and n in normalize(o["t"]):
                return o
        return None

    # ---------------- result parsing ----------------

    def _parse_results(self):
        """Scrape every table row rendered under #printMe into dicts."""
        rows = self.pg.evaluate(
            """() => {
              const pm = document.querySelector('#printMe') || document.body;
              const out = [];
              for (const tbl of pm.querySelectorAll('table')) {
                const trs = Array.from(tbl.rows);
                if (!trs.length) continue;
                const head = Array.from(trs[0].cells).map(c=>c.innerText.trim());
                if (!head.some(h=>/प्रत्याशी|नाम/i.test(h))) continue; // not a result table
                for (const r of trs.slice(1)) {
                  const cells = Array.from(r.cells).map(c=>c.innerText.trim());
                  if (cells.length !== head.length) continue;
                  out.push(Object.fromEntries(head.map((h,i)=>[h, cells[i]])));
                }
              }
              return out;
            }"""
        )
        mapped = []
        for r in rows:
            mapped.append(
                {
                    "district": r.get("जिला", ""),
                    "block": r.get("प्रखंड", ""),
                    "panchayat": r.get("पंचायत", ""),
                    "post": r.get("पद", ""),
                    "candidate": r.get("प्रत्याशी का नाम", ""),
                    "votes": int(re.sub(r"\D", "", r.get("कुल प्राप्त मत", "") or "0") or 0),
                    "winner": "(विजेता)" in r.get("प्रत्याशी का नाम", ""),
                }
            )
        return mapped

    # ---------------- leaf scrape ----------------

    def scrape_panchayat(self, post, district, block, panch):
        """Load fresh page, apply all filters silently, click Show once, parse."""
        last_err = None
        for attempt in range(1, RETRIES + 1):
            try:
                self._goto_fresh()
                self._select_post(post["v"])

                self._set_value("district", district["v"])
                self._click_show()

                self._set_value("block", block["v"])
                self._click_show()

                self._set_value("panchayat", panch["v"])
                self._click_show()

                rows = self._parse_results()
                return rows
            except Exception as e:
                last_err = str(e)[:120]
                log(f"    retry {attempt}/{RETRIES} {district['t']}/{block['t']}/{panch['t']}: {last_err}")
                time.sleep(2 * attempt)
        log(f"    FAILED {district['t']}/{block['t']}/{panch['t']}: {last_err}")
        return None

    def save_panchayat(self, post, district, block, panch, rows):
        folder = os.path.join(
            self.out_dir, slugify(post["t"]), slugify(district["t"]), slugify(block["t"])
        )
        os.makedirs(folder, exist_ok=True)
        fname = f"{slugify(panch['t'])}.json"
        payload = {
            "source": BASE_URL,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "filters": {
                "post": post,
                "district": district,
                "block": block,
                "panchayat": panch,
            },
            "candidate_count": len(rows),
            "candidates": sorted(rows, key=lambda r: -r["votes"]),
        }
        path = os.path.join(folder, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    # ---------------- traversal ----------------

    def walk(self, post, dist_filter=None, block_filter=None, panch_filter=None):
        """Scrape one post, traversing down to requested depth."""
        self._goto_fresh()
        self._select_post(post["v"])
        districts = self._options("district") or []
        if dist_filter:
            m = self.match_option(districts, dist_filter)
            if not m:
                log(f"district '{dist_filter}' not found for post '{post['t']}'"); return
            districts = [m]

        for di, district in enumerate(districts, 1):
            log(f"[{di}/{len(districts)}] district: {district['t']} ({district['v']})")
            self._goto_fresh()
            self._select_post(post["v"])
            self._set_value("district", district["v"])
            self._click_show()
            blocks = self._options("block") or []
            if block_filter:
                m = self.match_option(blocks, block_filter)
                if not m:
                    log(f"  block '{block_filter}' not found in {district['t']}"); continue
                blocks = [m]
            if not blocks:
                log(f"  no blocks for {district['t']}")

            for block in blocks:
                self._set_value("block", block["v"])
                self._click_show()
                panchayats = self._options("panchayat") or []
                if panch_filter:
                    m = self.match_option(panchayats, panch_filter)
                    if not m:
                        log(f"  panchayat '{panch_filter}' not found in {block['t']}"); continue
                    panchayats = [m]
                if not panchayats:
                    log(f"  no panchayats for {district['t']}/{block['t']}")

                for panch in panchayats:
                    rows = self.scrape_panchayat(post, district, block, panch)
                    if rows is None:
                        self.stats["failed"].append(
                            {"post": post["t"], "district": district["t"],
                             "block": block["t"], "panchayat": panch["t"]}
                        )
                        continue
                    if not rows:
                        self.stats["empty"] += 1
                    path = self.save_panchayat(post, district, block, panch, rows)
                    self.stats["scraped"] += 1
                    log(f"  ✔ {path} ({len(rows)} candidates)")

    # ---------------- listing ----------------

    def list_options(self, what, post=None, district=None, block=None):
        self._goto_fresh()
        if what == "posts":
            return self._options("post")
        self._select_post(post["v"])
        if what == "districts":
            return self._options("district")
        self._set_value("district", district["v"])
        self._click_show()
        if what == "blocks":
            return self._options("block")
        self._set_value("block", block["v"])
        self._click_show()
        if what == "panchayats":
            return self._options("panchayat")
        return []


# ---------------------------------------------------------------------- CLI

def resolve(matcher_opts, needle, kind, ctx_msg=""):
    m = Result7Scraper.match_option(matcher_opts, needle)
    if not m:
        names = ", ".join(o["t"] for o in matcher_opts[:40])
        sys.exit(f"✖ {kind} '{needle}' not found {ctx_msg}.\nAvailable: {names}")
    return m


def main():
    ap = argparse.ArgumentParser(
        description="Scrape Bihar 2021 claim/objection results into mirrored JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--post", help="post filter: name/value/slug e.g. sarpanch, मुखिया, 3")
    ap.add_argument("--district", help="district filter: name/value/slug e.g. मधुबनी / madhubani / 5")
    ap.add_argument("--block", help="block filter: name/value/slug e.g. मधवापुर / madhwapur")
    ap.add_argument("--panchayat", help="panchayat filter: name/value e.g. उत्तरा / 050010008")
    ap.add_argument("--list", choices=["posts", "districts", "blocks", "panchayats"],
                    help="just print the option tree (no scraping)")
    ap.add_argument("--out", default="data", help="output folder (default: ./data)")
    ap.add_argument("--headed", action="store_true", help="show browser window")
    args = ap.parse_args()

    s = Result7Scraper(headless=not args.headed, out_dir=args.out)
    s.start()
    try:
        posts = s._options("post") or []
        if not posts:
            sys.exit("✖ could not read post options from the site")

        # ---- listing mode ----
        if args.list:
            post = None
            if args.post:
                post = resolve(posts, args.post, "post")
            elif args.list != "posts":
                sys.exit("✖ --post is required for this listing")
            district = block = None
            if args.list in ("blocks", "panchayats"):
                if not post:
                    sys.exit("✖ --post required")
                s._select_post(post["v"])
                districts = s._options("district") or []
                if not args.district:
                    sys.exit("✖ --district required to list blocks/panchayats")
                district = resolve(districts, args.district, "district", f"under {post['t']}")
                s._set_value("district", district["v"]); s._click_show()
                blocks = s._options("block") or []
                if args.list == "panchayats":
                    if not args.block:
                        sys.exit("✖ --block required to list panchayats")
                    block = resolve(blocks, args.block, "block", f"under {district['t']}")
                    s._set_value("block", block["v"]); s._click_show()
                    opts = s._options("panchayat") or []
            elif args.list == "blocks":
                opts = blocks
            else:
                opts = districts if district else (s._options("district") if post else posts)
            if args.list == "posts":
                opts = posts
            print(json.dumps(opts, ensure_ascii=False, indent=2))
            return

        # ---- scrape mode ----
        if args.post:
            targets = [resolve(posts, args.post, "post")]
        else:
            targets = posts  # all posts

        s.stats["started"] = datetime.now(timezone.utc).isoformat()
        for post in targets:
            log(f"=== POST: {post['t']} ({post['v']}) ===")
            s.walk(post, args.district, args.block, args.panchayat)

        meta = {
            "source": BASE_URL,
            "started_at": s.stats["started"],
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "filters_used": {k: v for k, v in
                             {"post": args.post, "district": args.district,
                              "block": args.block, "panchayat": args.panchayat}.items() if v},
            "posts_scraped": [p["t"] for p in targets],
            "panchayats_scraped": s.stats["scraped"],
            "panchayats_empty": s.stats["empty"],
            "failures": s.stats["failed"],
        }
        os.makedirs(s.out_dir, exist_ok=True)
        with open(os.path.join(s.out_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        log(f"DONE. files={s.stats['scraped']} empty={s.stats['empty']} "
            f"failed={len(s.stats['failed'])} -> {s.out_dir}/")
    finally:
        s.stop()


if __name__ == "__main__":
    main()
