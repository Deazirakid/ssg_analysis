from fastapi import APIRouter, Depends

from .. import db
from ..auth import require_user
from ..db import Filters, filters_dep

router = APIRouter(prefix="/api/overview", tags=["overview"], dependencies=[Depends(require_user)])


@router.get("/kpis")
def kpis(f: Filters = Depends(filters_dep)):
    w, p = f.where()
    k = db.one(f"""SELECT count(*) listings,
        round(median(price_usd)) median_price, round(median(usd_per_m2)) median_m2,
        round(quantile_cont(usd_per_m2, .25)) p25_m2, round(quantile_cont(usd_per_m2, .75)) p75_m2,
        round(median(area_m2)) median_area,
        count(*) FILTER (WHERE created >= (SELECT max(created) FROM listings) - INTERVAL 7 DAY) new_7d,
        count(*) FILTER (WHERE created >= (SELECT max(created) FROM listings) - INTERVAL 14 DAY
                         AND created < (SELECT max(created) FROM listings) - INTERVAL 7 DAY) prev_7d,
        round(100.0 * avg(CASE WHEN is_project THEN 1 ELSE 0 END), 1) new_build_pct
        FROM listings WHERE {w}""", p)
    return k


@router.get("/neighbourhoods")
def neighbourhoods(f: Filters = Depends(filters_dep), limit: int = 25, min_n: int = 15):
    w, p = f.where(skip=("subdistrict",))
    return db.rows(f"""SELECT subdistrict name, district, count(*) n,
        round(median(usd_per_m2)) median_m2, round(median(price_usd)) median_price
        FROM listings WHERE {w} AND subdistrict IS NOT NULL
        GROUP BY 1,2 HAVING count(*) >= ? ORDER BY n DESC LIMIT ?""", p + [min_n, limit])


@router.get("/daily")
def daily(f: Filters = Depends(filters_dep), days: int = 60):
    w, p = f.where()
    return db.rows(f"""SELECT strftime(created, '%Y-%m-%d') d, count(*) n, round(median(usd_per_m2)) m2
        FROM listings WHERE {w} AND created >= (SELECT max(created) FROM listings) - to_days(?)
        GROUP BY 1 ORDER BY 1""", p + [days])


@router.get("/histogram")
def histogram(f: Filters = Depends(filters_dep), metric: str = "usd_per_m2", bins: int = 24):
    col = {"usd_per_m2": "usd_per_m2", "price_usd": "price_usd", "area_m2": "area_m2"}.get(metric, "usd_per_m2")
    w, p = f.where()
    lim = db.one(f"SELECT quantile_cont({col}, .01) lo, quantile_cont({col}, .98) hi FROM listings "
                 f"WHERE {w} AND {col} > 0", p)
    if lim.get("lo") is None:
        return {"bins": [], "metric": col}
    lo, hi = float(lim["lo"]), float(lim["hi"])
    width = max((hi - lo) / bins, 1e-9)
    r = db.rows(f"""SELECT least(floor(({col} - ?) / ?), ? - 1)::INT b, count(*) n FROM listings
        WHERE {w} AND {col} >= ? GROUP BY 1 ORDER BY 1""", [lo, width, bins] + p + [lo])
    counts = {x["b"]: x["n"] for x in r}
    return {"metric": col, "bins": [{"from": round(lo + i * width), "to": round(lo + (i + 1) * width),
                                     "n": counts.get(i, 0)} for i in range(bins)]}


@router.get("/mix")
def mix(f: Filters = Depends(filters_dep)):
    """Listing count by type x deal (ignores the type/deal filter so the mix is visible)."""
    w, p = f.where(skip=("type", "deal"))
    return db.rows(f"SELECT type, deal, count(*) n FROM listings WHERE {w} GROUP BY 1,2 ORDER BY n DESC", p)


@router.get("/rooms")
def rooms(f: Filters = Depends(filters_dep)):
    w, p = f.where()
    return db.rows(f"""SELECT CASE WHEN rooms >= 5 THEN '5+' ELSE CAST(CAST(rooms AS INTEGER) AS VARCHAR) END r,
        count(*) n, round(median(usd_per_m2)) median_m2, round(median(price_usd)) median_price,
        round(median(area_m2)) median_area
        FROM listings WHERE {w} AND rooms BETWEEN 1 AND 20 GROUP BY 1 ORDER BY 1""", p)
