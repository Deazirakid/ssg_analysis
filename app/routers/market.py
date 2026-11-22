"""Market intelligence: deals, price drops, days-on-market, trends, compare, projects, sellers,
fraud, seasonal rentals, distance-to-metro/centre, investment context."""
from fastapi import APIRouter, Depends, HTTPException, Query

from .. import db
from ..auth import require_user
from ..db import Filters, filters_dep

router = APIRouter(prefix="/api/market", tags=["market"], dependencies=[Depends(require_user)])

L_COLS = "id, title, type, deal, subdistrict, street, price_usd, usd_per_m2, area_m2, rooms, floor, is_project, url, created"


def _runs():
    return [r["run"] for r in db.rows("SELECT DISTINCT run FROM history ORDER BY run DESC")]


@router.get("/runs", summary="Scrape runs available in the history window")
def runs():
    return db.rows("SELECT run, count(*) listings, round(median(usd_per_m2)) median_m2 FROM history GROUP BY 1 ORDER BY 1")


@router.get("/deals", summary="Below-market listings (vs neighbourhood + room-count median)")
def deals(f: Filters = Depends(filters_dep), min_discount: float = 15, max_discount: float = 60, limit: int = 100,
          min_bench: int = 8):
    """Discounts above `max_discount` are usually data errors (wrong area/price); see /api/market/fraud."""
    w, p = f.where()
    return db.rows(f"""WITH f AS (SELECT *, CASE WHEN rooms >= 4 THEN 4 ELSE coalesce(rooms, 0) END rb FROM listings WHERE {w})
        SELECT {', '.join('f.' + c.strip() for c in L_COLS.split(','))}, round(b.b_m2) bench_m2, b.bn bench_n,
               round(100 * (1 - f.usd_per_m2 / b.b_m2), 1) discount_pct,
               round((b.b_m2 - f.usd_per_m2) * f.area_m2) saving_usd
        FROM f JOIN bench b USING (type, deal, subdistrict, rb)
        WHERE b.bn >= ? AND f.usd_per_m2 > 0 AND 100 * (1 - f.usd_per_m2 / b.b_m2) BETWEEN ? AND ?
        ORDER BY discount_pct DESC LIMIT ?""", p + [min_bench, min_discount, max_discount, min(limit, 500)])


@router.get("/drops", summary="Price changes between the two latest scrape runs")
def drops(f: Filters = Depends(filters_dep), direction: str = "down", limit: int = 200):
    rs = _runs()
    if len(rs) < 2:
        return {"runs": rs, "summary": None, "rows": [],
                "message": "Need at least 2 scrape runs. Run the pipeline again to start tracking price changes."}
    cur, prev = rs[0], rs[1]
    w, p = f.where()
    base = f"""WITH f AS (SELECT * FROM listings WHERE {w}),
        pr AS (SELECT id, price_usd old_price FROM history WHERE run = ?)
        SELECT {', '.join('f.' + c.strip() for c in L_COLS.split(','))}, pr.old_price,
               round(f.price_usd - pr.old_price) change_usd, round(100 * (f.price_usd / pr.old_price - 1), 1) change_pct
        FROM f JOIN pr USING (id) WHERE pr.old_price > 0 AND f.price_usd <> pr.old_price"""
    summ = db.one(f"""SELECT count(*) changed, count(*) FILTER (WHERE change_usd < 0) drops,
        count(*) FILTER (WHERE change_usd > 0) rises, round(median(change_pct) FILTER (WHERE change_usd < 0), 1) median_drop_pct
        FROM ({base})""", p + [prev])
    order = "change_pct ASC" if direction == "down" else "change_pct DESC"
    cond = "change_usd < 0" if direction == "down" else "change_usd > 0"
    rows = db.rows(f"SELECT * FROM ({base}) WHERE {cond} ORDER BY {order} LIMIT ?", p + [prev, min(limit, 1000)])
    return {"runs": [prev, cur], "summary": summ, "rows": rows}


@router.get("/dom", summary="Days on market & delisting (sell-through proxy)")
def days_on_market(f: Filters = Depends(filters_dep)):
    w, p = f.where()
    snap = "(SELECT max(created) FROM listings)"
    buckets = db.rows(f"""SELECT CASE WHEN d < 7 THEN '< 1 week' WHEN d < 30 THEN '1-4 weeks' WHEN d < 90 THEN '1-3 months'
              WHEN d < 180 THEN '3-6 months' WHEN d < 365 THEN '6-12 months' ELSE '1 year +' END bucket,
              min(d) ord, count(*) n, round(median(usd_per_m2)) median_m2
        FROM (SELECT date_diff('day', created, {snap}) d, usd_per_m2 FROM listings WHERE {w}) GROUP BY 1 ORDER BY ord""", p)
    by_area = db.rows(f"""SELECT subdistrict name, count(*) n, round(median(date_diff('day', created, {snap}))) median_days,
            round(100.0 * avg(CASE WHEN date_diff('day', created, {snap}) > 90 THEN 1 ELSE 0 END), 1) stale_pct
        FROM listings WHERE {w} AND subdistrict IS NOT NULL GROUP BY 1 HAVING count(*) >= 20 ORDER BY median_days""", p)
    rs = _runs()
    through = None
    if len(rs) >= 2:
        # previous-run ids that are no longer in the current feed (sold, expired or withdrawn)
        through = db.rows("""WITH prev AS (SELECT id FROM history WHERE run = ?),
              cur AS (SELECT id FROM history WHERE run = ?)
            SELECT count(*) prev_n, count(*) FILTER (WHERE cur.id IS NULL) gone
            FROM prev LEFT JOIN cur USING (id)""", [rs[1], rs[0]])[0]
        through["rate_pct"] = round(100 * through["gone"] / through["prev_n"], 2) if through["prev_n"] else None
        through["runs"] = [rs[1], rs[0]]
    return {"buckets": buckets, "by_area": by_area, "delisting": through}


@router.get("/trends", summary="Weekly median asking price of newly listed properties")
def trends(f: Filters = Depends(filters_dep), weeks: int = 52, by: str = ""):
    w, p = f.where(skip=("subdistrict",) if by == "subdistrict" else ())
    if by == "subdistrict":
        top = [r["subdistrict"] for r in db.rows(f"""SELECT subdistrict, count(*) n FROM listings WHERE {w}
              AND subdistrict IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 6""", p)]
        if f.subdistrict:
            top = f.subdistrict[:6]
        if not top:
            return {"series": {}}
        rows = db.rows(f"""SELECT subdistrict s, strftime(date_trunc('week', created), '%Y-%m-%d') wk, count(*) n,
              round(median(usd_per_m2)) m2 FROM listings WHERE {w} AND subdistrict IN ({','.join('?' * len(top))})
              AND created >= (SELECT max(created) FROM listings) - to_weeks(?) GROUP BY 1,2 ORDER BY 2""",
                       p + top + [weeks])
        series = {}
        for r in rows:
            series.setdefault(r["s"], []).append(r)
        return {"series": series}
    return {"weekly": db.rows(f"""SELECT strftime(date_trunc('week', created), '%Y-%m-%d') wk, count(*) n,
          round(median(usd_per_m2)) m2, round(median(price_usd)) price FROM listings WHERE {w}
          AND created >= (SELECT max(created) FROM listings) - to_weeks(?) GROUP BY 1 ORDER BY 1""", p + [weeks]),
            "by_run": db.rows("SELECT run, count(*) n, round(median(usd_per_m2)) m2 FROM history GROUP BY 1 ORDER BY 1")}


@router.get("/compare", summary="Side-by-side comparison of up to 4 neighbourhoods")
def compare(f: Filters = Depends(filters_dep), areas: str = Query(..., description="comma-separated subdistricts")):
    names = [a for a in areas.split(",") if a][:4]
    if not names:
        raise HTTPException(400, "areas required")
    w, p = f.where(skip=("subdistrict", "district"))
    ph = ",".join("?" * len(names))
    stats = db.rows(f"""SELECT subdistrict name, count(*) n, round(median(price_usd)) median_price,
          round(median(usd_per_m2)) median_m2, round(quantile_cont(usd_per_m2, .25)) p25, round(quantile_cont(usd_per_m2, .75)) p75,
          round(median(area_m2)) median_area, round(100.0 * avg(CASE WHEN is_project THEN 1 ELSE 0 END), 1) new_build_pct,
          round(median(date_diff('day', created, (SELECT max(created) FROM listings)))) median_days,
          round(median(metro_km), 2) metro_km, round(median(dist_center_km), 2) center_km
        FROM listings WHERE {w} AND subdistrict IN ({ph}) GROUP BY 1""", p + names)
    rent = {r["subdistrict"]: r for r in db.rows(f"""SELECT subdistrict, median(usd_per_m2) rent_m2, median(price_usd) rent
        FROM listings WHERE deal = 'Rent' AND subdistrict IN ({ph}) {'AND type IN (' + ','.join('?' * len(f.type)) + ')' if f.type else ''}
        GROUP BY 1""", names + f.type)}
    for s in stats:
        r = rent.get(s["name"])
        s["median_rent"] = round(r["rent"]) if r and r["rent"] else None
        s["yield_pct"] = round(r["rent_m2"] * 12 / s["median_m2"] * 100, 2) if r and r["rent_m2"] and s["median_m2"] else None
    rooms = db.rows(f"""SELECT subdistrict name, CASE WHEN rooms >= 5 THEN '5+' ELSE CAST(CAST(rooms AS INTEGER) AS VARCHAR) END r,
          count(*) n, round(median(usd_per_m2)) m2 FROM listings WHERE {w} AND subdistrict IN ({ph}) AND rooms >= 1
          GROUP BY 1,2 ORDER BY 2""", p + names)
    return {"stats": sorted(stats, key=lambda s: names.index(s["name"])), "rooms": rooms}


@router.get("/projects", summary="Buildings & new-build projects (listings sharing one exact building pin)")
def projects(f: Filters = Depends(filters_dep), min_units: int = 4, limit: int = 150):
    """ss.ge's homeId is per listing, so units are grouped by their exact map pin (≈ one building)."""
    w, p = f.where(skip=("segment",))
    return db.rows(f"""WITH f AS (SELECT *, CAST(round(lat, 4) AS VARCHAR) || ',' || CAST(round(lon, 4) AS VARCHAR) bkey FROM listings
            WHERE {w} AND coord_precision = 'exact' AND NOT flag_generic_pin),
        resale AS (SELECT subdistrict, median(usd_per_m2) resale_m2 FROM f WHERE NOT is_project GROUP BY 1)
        SELECT bkey building, any_value(subdistrict) subdistrict, mode(street) street, count(*) units,
               round(100.0 * avg(CASE WHEN is_project THEN 1 ELSE 0 END)) new_build_pct,
               max(floors_total) floors, round(median(usd_per_m2)) median_m2,
               round(min(price_usd)) min_price, round(max(price_usd)) max_price, round(median(area_m2)) median_area,
               round(avg(lat), 5) lat, round(avg(lon), 5) lon, round(any_value(r.resale_m2)) resale_m2,
               round(100 * (median(usd_per_m2) / any_value(r.resale_m2) - 1), 1) premium_pct,
               count(DISTINCT poster) sellers, any_value(url) sample_url
        FROM f LEFT JOIN resale r USING (subdistrict)
        GROUP BY bkey HAVING count(*) >= ? ORDER BY new_build_pct DESC, units DESC LIMIT ?""",
                   p + [min_units, min(limit, 500)])


@router.get("/sellers", summary="Broker vs owner split (poster with ≥ N active listings = broker/agency)")
def sellers(f: Filters = Depends(filters_dep), broker_min: int = 5):
    w, p = f.where()
    base = f"""SELECT l.*, CASE WHEN ps.poster_n >= ? THEN 'Broker / agency' WHEN ps.poster_n IS NULL THEN 'Unknown'
               ELSE 'Private owner' END seller FROM listings l LEFT JOIN poster_stats ps USING (poster) WHERE {w}"""
    split = db.rows(f"""SELECT seller, count(*) n, round(median(usd_per_m2)) median_m2, round(median(price_usd)) median_price
        FROM ({base}) GROUP BY 1 ORDER BY n DESC""", [broker_min] + p)
    by_area = db.rows(f"""SELECT subdistrict name, count(*) n,
          round(100.0 * avg(CASE WHEN seller = 'Broker / agency' THEN 1 ELSE 0 END), 1) broker_pct,
          round(median(usd_per_m2) FILTER (WHERE seller = 'Broker / agency')) broker_m2,
          round(median(usd_per_m2) FILTER (WHERE seller = 'Private owner')) owner_m2
        FROM ({base}) WHERE subdistrict IS NOT NULL GROUP BY 1 HAVING count(*) >= 30 ORDER BY broker_pct DESC""",
                      [broker_min] + p)
    top = db.rows(f"""SELECT poster, count(*) n, count(DISTINCT subdistrict) areas, round(median(usd_per_m2)) median_m2,
          string_agg(DISTINCT type, ', ') types
        FROM listings WHERE {w} AND poster IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 25""", p)
    return {"split": split, "by_area": by_area, "top_posters": top}


@router.get("/fraud", summary="Duplicate / suspicious listing monitor")
def fraud(f: Filters = Depends(filters_dep), limit: int = 100):
    w, p = f.where()
    low = db.rows(f"""WITH f AS (SELECT *, CASE WHEN rooms >= 4 THEN 4 ELSE coalesce(rooms, 0) END rb FROM listings WHERE {w})
        SELECT {', '.join('f.' + c.strip() for c in L_COLS.split(','))}, round(b.b_m2) bench_m2,
               round(100 * (1 - f.usd_per_m2 / b.b_m2), 1) discount_pct, ps.poster_n
        FROM f JOIN bench b USING (type, deal, subdistrict, rb) LEFT JOIN poster_stats ps USING (poster)
        WHERE b.bn >= 10 AND f.usd_per_m2 < b.b_m2 * 0.5 ORDER BY discount_pct DESC LIMIT ?""", p + [limit])
    tw, tp = f.where(skip=("type", "deal"))
    dups = db.rows(f"""SELECT * FROM duplicates WHERE 1=1
        {'AND type IN (' + ','.join('?' * len(f.type)) + ')' if f.type else ''}
        {'AND deal IN (' + ','.join('?' * len(f.deal)) + ')' if f.deal else ''}
        ORDER BY n DESC LIMIT ?""", f.type + f.deal + [limit])
    same_title = db.rows(f"""SELECT title, count(*) n, count(DISTINCT price_usd) prices, count(DISTINCT subdistrict) areas,
          min(price_usd) min_price, max(price_usd) max_price
        FROM listings WHERE {w} AND title IS NOT NULL GROUP BY 1
        HAVING count(DISTINCT subdistrict) >= 4 AND count(*) >= 8 ORDER BY n DESC LIMIT 30""", p)
    summary = {"low_price": len(low), "dup_clusters": db.one("SELECT count(*) n, sum(n) listings FROM duplicates"),
               "heavy_posters": db.one("SELECT count(*) n FROM poster_stats WHERE poster_n >= 50")["n"]}
    return {"summary": summary, "low_price": low, "duplicates": dups, "same_title": same_title}


TOURIST = ["ბათუმი", "ბაკურიანი", "გუდაური", "ქობულეთი", "ბორჯომი", "სიღნაღი", "ურეკი", "თბილისი"]


@router.get("/seasonal", summary="Daily-rent supply & price by month listed (tourist places)")
def seasonal(places: str = ""):
    pl = [x for x in places.split(",") if x] or TOURIST
    ph = ",".join("?" * len(pl))
    monthly = db.rows(f"""SELECT city, strftime(created, '%Y-%m') m, count(*) n, round(median(price_usd)) price
        FROM listings WHERE deal = 'Daily rent' AND city IN ({ph}) AND created >= (SELECT max(created) FROM listings) - INTERVAL 24 MONTH
        GROUP BY 1,2 ORDER BY 2""", pl)
    by_city = db.rows(f"""SELECT city, count(*) n, round(median(price_usd)) median_night, round(quantile_cont(price_usd, .75)) p75_night,
          string_agg(DISTINCT type, ', ') types FROM listings WHERE deal = 'Daily rent' AND city IN ({ph})
        GROUP BY 1 ORDER BY n DESC""", pl)
    moy = db.rows(f"""SELECT strftime(created, '%m') mo, count(*) n, round(median(price_usd)) price
        FROM listings WHERE deal = 'Daily rent' AND city IN ({ph}) GROUP BY 1 ORDER BY 1""", pl)
    return {"places": pl, "monthly": monthly, "by_city": by_city, "month_of_year": moy}


@router.get("/distance", summary="Price vs distance to nearest metro / city centre (Tbilisi)")
def distance(f: Filters = Depends(filters_dep)):
    w, p = f.where()
    metro = db.rows(f"""SELECT least(floor(metro_km / 0.25) * 0.25, 3.0) km, count(*) n, round(median(usd_per_m2)) m2
        FROM listings WHERE {w} AND metro_km IS NOT NULL AND coord_precision IN ('exact','street')
        GROUP BY 1 ORDER BY 1""", p)
    center = db.rows(f"""SELECT least(floor(dist_center_km), 15) km, count(*) n, round(median(usd_per_m2)) m2
        FROM listings WHERE {w} AND dist_center_km IS NOT NULL AND coord_precision IN ('exact','street')
        GROUP BY 1 ORDER BY 1""", p)
    stations = db.rows(f"""SELECT metro_name name, count(*) n, round(median(usd_per_m2)) m2, round(median(metro_km), 2) km
        FROM listings WHERE {w} AND metro_km <= 0.8 AND coord_precision IN ('exact','street')
        GROUP BY 1 HAVING count(*) >= 10 ORDER BY m2 DESC""", p)
    return {"metro": metro, "center": center, "stations": stations}


@router.get("/invest/{lid}", summary="Investment context for a listing: rent benchmarks")
def invest(lid: int):
    l = db.one(f"SELECT {L_COLS}, district, city, metro_name, metro_km FROM listings WHERE id = ?", [lid])
    if not l:
        raise HTTPException(404, "listing not found")
    rb = db.one("""SELECT round(median(price_usd)) rent, round(median(usd_per_m2), 2) rent_m2, count(*) n
        FROM listings WHERE deal = 'Rent' AND type = ? AND subdistrict = ?
        AND (? IS NULL OR rooms = ?)""", [l["type"], l["subdistrict"], l["rooms"], l["rooms"]])
    ra = db.one("""SELECT round(median(usd_per_m2), 2) rent_m2, count(*) n FROM listings
        WHERE deal = 'Rent' AND type = ? AND subdistrict = ?""", [l["type"], l["subdistrict"]])
    est = round(ra["rent_m2"] * l["area_m2"]) if ra.get("rent_m2") and l.get("area_m2") else None
    return {"listing": l, "rent_same_rooms": rb, "rent_area": ra, "estimated_rent": rb.get("rent") or est}
