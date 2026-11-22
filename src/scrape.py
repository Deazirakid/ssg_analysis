"""Scrape ss.ge real-estate listings (all property types x deal types).

Phase 1  MapSearch     -> every pin: id, lat/lon, price (1 call per combo)
Phase 2  LegendSearch  -> listing attributes, paged 30/page, threaded

Output: data/raw/<run>/map.jsonl, list.jsonl, meta.json
"""
import argparse
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

sys.path.insert(0, str(Path(__file__).parent))
from token_provider import TokenProvider  # noqa: E402

API = "https://api-gateway.ss.ge/v1/RealEstate"
PAGE_SIZE = 30  # API rejects > 30
ROOT = Path(__file__).resolve().parents[1]

TYPES = {1: "Country house", 2: "Hotel", 3: "Land", 4: "House", 5: "Apartment", 6: "Commercial"}
DEALS = {1: "Rent", 2: "Pledge", 3: "Daily rent", 4: "Sale"}

_local = threading.local()
_tokens = TokenProvider()
_stats = {"req": 0, "retry": 0, "fail": 0}
_stats_lock = threading.Lock()


def default_workers():
    # I/O bound: ~3 threads per logical core, floor 30, cap 64
    return max(30, min(64, (os.cpu_count() or 8) * 3))


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=4))
        s.headers.update({
            "Origin": "https://home.ss.ge",
            "Referer": "https://home.ss.ge/",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": "ka",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        })
        _local.s = s
    return s


def post(endpoint, body, timeout=60, tries=7):
    tok = _tokens.get()
    for attempt in range(tries):
        with _stats_lock:
            _stats["req"] += 1
        try:
            r = session().post(f"{API}/{endpoint}", json=body, timeout=timeout,
                               headers={"Authorization": f"Bearer {tok}"})
            if r.status_code == 200:
                return r.json()
            if r.status_code == 401:
                tok = _tokens.invalidate(tok)
                continue
            if r.status_code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"{endpoint} HTTP {r.status_code}: {r.text[:200]}")
        except (requests.RequestException, ValueError):
            pass
        with _stats_lock:
            _stats["retry"] += 1
        time.sleep(min(30, 1.5 ** attempt + random.random()))
    with _stats_lock:
        _stats["fail"] += 1
    raise RuntimeError(f"{endpoint} failed after {tries} tries: {body}")


def body(t, d, page=1):
    return {"realEstateType": t, "realEstateDealType": d, "page": page,
            "pageSize": PAGE_SIZE, "order": 1}


def page_items(t, d, page):
    return post("LegendSearch", body(t, d, page)).get("realStateItemModel") or []


def last_page(t, d):
    """Exponential probe + binary search for the last non-empty page."""
    if not page_items(t, d, 1):
        return 0
    lo, hi = 1, 2
    while page_items(t, d, hi):
        lo, hi = hi, hi * 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if page_items(t, d, mid):
            lo = mid
        else:
            hi = mid
    return lo


NEXT_RX = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def detail_coords(item, tries=4):
    """Fallback: read lat/lon from the public listing page's embedded JSON."""
    url = f"https://home.ss.ge/ka/udzravi-qoneba/x-{item['applicationId']}"
    for attempt in range(tries):
        try:
            r = session().get(url, timeout=40, headers={"Accept": "text/html"})
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                m = NEXT_RX.search(r.text)
                a = (json.loads(m.group(1))["props"]["pageProps"].get("applicationData") or {}) if m else {}
                lat, lon = a.get("locationLatitude"), a.get("locationLongitude")
                if not lat:
                    return None
                return {"applicationId": item["applicationId"], "price": item.get("price"),
                        "locationLatitude": lat, "locationLongitude": lon,
                        "isManualPin": a.get("isManualPin"), "type": item.get("type"),
                        "dealType": item.get("dealType"), "src": "detail"}
        except (requests.RequestException, ValueError, KeyError):
            pass
        time.sleep(1.5 ** attempt + random.random())
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=default_workers())
    ap.add_argument("--types", default="1,2,3,4,5,6")
    ap.add_argument("--deals", default="1,2,3,4")
    ap.add_argument("--skip-list", action="store_true", help="only MapSearch")
    ap.add_argument("--detail-fallback", action="store_true",
                    help="fetch detail pages for unpinned listings (slow, rate-limited)")
    args = ap.parse_args()

    combos = [(int(t), int(d)) for t in args.types.split(",") for d in args.deals.split(",")]
    run = datetime.now().strftime("%Y%m%d_%H%M")
    out = ROOT / "data" / "raw" / run
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print(f"run={run} workers={args.workers} combos={len(combos)}", flush=True)
    _tokens.get()

    # ---- Phase 1: MapSearch (coords + price for every pin) ----
    map_counts = {}
    with open(out / "map.jsonl", "w", encoding="utf-8") as fm, \
            ThreadPoolExecutor(max_workers=min(8, args.workers)) as ex:
        futs = {ex.submit(post, "MapSearch", body(t, d), 300): (t, d) for t, d in combos}
        for f in as_completed(futs):
            t, d = futs[f]
            try:
                items = f.result().get("realStateMapItemModel") or []
            except RuntimeError as e:
                print(f"[map] {TYPES[t]} {DEALS[d]} FAILED ({e}); detail fallback will fill coords",
                      flush=True)
                map_counts[f"{t}-{d}"] = "failed"
                continue
            for it in items:
                it["type"], it["dealType"] = t, d
                fm.write(json.dumps(it, ensure_ascii=False) + "\n")
            map_counts[f"{t}-{d}"] = len(items)
            print(f"[map] {TYPES[t]:<13} {DEALS[d]:<10} {len(items):>7} pins", flush=True)
    print(f"[map] total {sum(v for v in map_counts.values() if isinstance(v, int))} pins "
          f"in {time.time()-t0:.0f}s", flush=True)

    list_counts = {}
    if not args.skip_list:
        # ---- Phase 2a: find page counts ----
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            lp = dict(zip(combos, ex.map(lambda c: last_page(*c), combos)))
        jobs = [(t, d, p) for (t, d), n in lp.items() for p in range(1, n + 1)]
        print(f"[list] {len(jobs)} pages to fetch (~{len(jobs)*PAGE_SIZE} listings)", flush=True)

        # ---- Phase 2b: fetch all pages ----
        seen, done = set(), 0
        wlock = threading.Lock()
        with open(out / "list.jsonl", "w", encoding="utf-8") as fl, \
                ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(page_items, *j): j for j in jobs}
            for f in as_completed(futs):
                t, d, p = futs[f]
                try:
                    items = f.result()
                except RuntimeError as e:
                    print(f"[list] page fail {t}-{d}-{p}: {e}", flush=True)
                    continue
                with wlock:
                    for it in items:
                        if it["applicationId"] in seen:
                            continue
                        seen.add(it["applicationId"])
                        fl.write(json.dumps(it, ensure_ascii=False) + "\n")
                        k = f"{t}-{d}"
                        list_counts[k] = list_counts.get(k, 0) + 1
                done += 1
                if done % 250 == 0 or done == len(jobs):
                    el = time.time() - t0
                    print(f"[list] {done}/{len(jobs)} pages, {len(seen)} unique, "
                          f"{_stats['retry']} retries, {el:.0f}s", flush=True)

    if not args.skip_list and args.detail_fallback:
        # ---- Phase 3 (optional): coords from detail pages for listings with no map pin ----
        # Note: unpinned listings usually have null coords on ss.ge too, and home.ss.ge
        # rate-limits (429) heavy page fetching; clean.py imputes street/subdistrict coords.
        pinned = set()
        with open(out / "map.jsonl", encoding="utf-8") as fm:
            for line in fm:
                pinned.add(json.loads(line)["applicationId"])
        missing = []
        with open(out / "list.jsonl", encoding="utf-8") as fl:
            for line in fl:
                it = json.loads(line)
                if it["applicationId"] not in pinned:
                    missing.append(it)
        print(f"[detail] {len(missing)} listings without pin -> fetching detail pages", flush=True)
        got = 0
        with open(out / "map.jsonl", "a", encoding="utf-8") as fm, \
                ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(detail_coords, it): it for it in missing}
            for i, f in enumerate(as_completed(futs), 1):
                res = f.result()
                if res:
                    fm.write(json.dumps(res, ensure_ascii=False) + "\n")
                    got += 1
                if i % 1000 == 0 or i == len(missing):
                    print(f"[detail] {i}/{len(missing)}, {got} with coords, {time.time()-t0:.0f}s",
                          flush=True)
        map_counts["detail_fallback"] = got

    meta = {"run": run, "finished": datetime.now().isoformat(timespec="seconds"),
            "seconds": round(time.time() - t0), "workers": args.workers,
            "map_counts": map_counts, "list_counts": list_counts, "http": _stats}
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    (ROOT / "data" / "raw" / "LATEST").write_text(run, encoding="utf-8")
    print(json.dumps(meta, indent=1), flush=True)


if __name__ == "__main__":
    main()
