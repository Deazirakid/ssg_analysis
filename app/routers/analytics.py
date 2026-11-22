from fastapi import APIRouter, Depends

from .. import db
from ..auth import require_user
from ..db import Filters, filters_dep

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_user)])


@router.get("/yield")
def rental_yield(f: Filters = Depends(filters_dep), min_n: int = 15, limit: int = 30):
    """Gross yield per neighbourhood = median rent $/m2 x 12 / median sale $/m2 (same type)."""
    w, p = f.where(skip=("deal",))
    return db.rows(f"""WITH s AS (
          SELECT subdistrict, count(*) n_sale, median(usd_per_m2) sale_m2, median(price_usd) sale_price
          FROM listings WHERE {w} AND deal = 'Sale' AND subdistrict IS NOT NULL GROUP BY 1),
        r AS (
          SELECT subdistrict, count(*) n_rent, median(usd_per_m2) rent_m2, median(price_usd) rent
          FROM listings WHERE {w} AND deal = 'Rent' AND subdistrict IS NOT NULL GROUP BY 1)
        SELECT s.subdistrict name, n_sale, n_rent, round(sale_m2) sale_m2, round(rent, 0) rent,
               round(rent_m2, 2) rent_m2, round(sale_price) sale_price,
               round(rent_m2 * 12 / sale_m2 * 100, 2) yield_pct,
               round(sale_price / nullif(rent * 12, 0), 1) payback_years
        FROM s JOIN r USING (subdistrict)
        WHERE n_sale >= ? AND n_rent >= ?
        ORDER BY yield_pct DESC LIMIT ?""", p + p + [min_n, min_n, limit])


@router.get("/scatter")
def scatter(f: Filters = Depends(filters_dep), n: int = 2500):
    n = int(min(max(n, 100), 10000))  # sample size must be a literal in DuckDB
    w, p = f.where()
    return db.rows(f"""SELECT * FROM (SELECT area_m2 x, price_usd y, usd_per_m2 m2, rooms, subdistrict
        FROM listings WHERE {w} AND area_m2 > 0 AND price_usd > 0)
        USING SAMPLE reservoir({n} ROWS) REPEATABLE (7)""", p)


@router.get("/floors")
def floors(f: Filters = Depends(filters_dep)):
    w, p = f.where()
    return db.rows(f"""SELECT CASE WHEN floor <= 0 THEN 'Basement/0' WHEN floor = 1 THEN '1'
              WHEN floor <= 3 THEN '2-3' WHEN floor <= 6 THEN '4-6' WHEN floor <= 10 THEN '7-10'
              WHEN floor <= 15 THEN '11-15' ELSE '16+' END bucket,
            min(floor) ord, count(*) n, round(median(usd_per_m2)) median_m2
        FROM listings WHERE {w} AND floor IS NOT NULL GROUP BY 1 ORDER BY ord""", p)


@router.get("/segments")
def segments(f: Filters = Depends(filters_dep)):
    w, p = f.where()
    seg = db.rows(f"""SELECT CASE WHEN is_project THEN 'New build' ELSE 'Resale' END k, count(*) n,
        round(median(usd_per_m2)) median_m2, round(median(price_usd)) median_price
        FROM listings WHERE {w} GROUP BY 1 ORDER BY 1""", p)
    furn = db.rows(f"""SELECT CASE WHEN furniture THEN 'Furnished' ELSE 'Unfurnished' END k, count(*) n,
        round(median(usd_per_m2)) median_m2, round(median(price_usd)) median_price
        FROM listings WHERE {w} GROUP BY 1 ORDER BY 1""", p)
    metro = db.rows(f"""SELECT CASE WHEN near_subway IS NOT NULL THEN 'Near metro' ELSE 'No metro nearby' END k,
        count(*) n, round(median(usd_per_m2)) median_m2, round(median(price_usd)) median_price
        FROM listings WHERE {w} GROUP BY 1 ORDER BY 1""", p)
    return {"build": seg, "furniture": furn, "metro": metro}


@router.get("/streets")
def streets(f: Filters = Depends(filters_dep), min_n: int = 10, limit: int = 25):
    w, p = f.where()
    return db.rows(f"""SELECT street, any_value(subdistrict) subdistrict, count(*) n,
        round(median(usd_per_m2)) median_m2, round(median(price_usd)) median_price
        FROM listings WHERE {w} AND street IS NOT NULL GROUP BY 1 HAVING count(*) >= ?
        ORDER BY median_m2 DESC LIMIT ?""", p + [min_n, limit])


@router.get("/districts")
def districts(f: Filters = Depends(filters_dep)):
    w, p = f.where(skip=("district", "subdistrict"))
    return db.rows(f"""SELECT district name, count(*) n, round(median(usd_per_m2)) median_m2,
        round(quantile_cont(usd_per_m2, .25)) p25, round(quantile_cont(usd_per_m2, .75)) p75,
        round(median(price_usd)) median_price, round(median(area_m2)) median_area
        FROM listings WHERE {w} AND district IS NOT NULL GROUP BY 1 HAVING count(*) >= 10
        ORDER BY median_m2 DESC""", p)
