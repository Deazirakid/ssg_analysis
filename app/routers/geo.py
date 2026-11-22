"""Map data: compact point arrays (client builds GeoJSON) + grid aggregation."""
from fastapi import APIRouter, Depends

from .. import db
from ..auth import require_user
from ..db import Filters, filters_dep

router = APIRouter(prefix="/api/map", tags=["map"], dependencies=[Depends(require_user)])

PRECISE = "coord_precision IN ('exact','street') AND NOT flag_generic_pin AND lat IS NOT NULL"


@router.get("/points")
def points(f: Filters = Depends(filters_dep), limit: int = 60000):
    w, p = f.where()
    c = db.cur()
    res = c.execute(f"""SELECT id, round(lat, 5), round(lon, 5), price_usd, usd_per_m2, area_m2, rooms,
            coord_precision = 'exact'
        FROM listings WHERE {w} AND {PRECISE} LIMIT ?""", p + [min(limit, 150000)]).fetchall()
    total = c.execute(f"SELECT count(*) FROM listings WHERE {w}", p).fetchone()[0]
    return {"fields": ["id", "lat", "lon", "price", "m2", "area", "rooms", "exact"],
            "rows": [list(r) for r in res], "total_filtered": total}


@router.get("/grid")
def grid(f: Filters = Depends(filters_dep), cell: float = 0.004, metric: str = "usd_per_m2", min_n: int = 3):
    col = {"usd_per_m2": "usd_per_m2", "price_usd": "price_usd"}.get(metric, "usd_per_m2")
    cell = min(max(cell, 0.001), 0.05)
    w, p = f.where()
    r = db.rows(f"""SELECT floor(lat / ?)::INT gy, floor(lon / ?)::INT gx, count(*) n,
            round(median({col})) v, round(median(area_m2)) area
        FROM listings WHERE {w} AND {PRECISE} AND {col} > 0
        GROUP BY 1,2 HAVING count(*) >= ?""", [cell, cell] + p + [min_n])
    return {"cell": cell, "metric": col, "cells": r}


@router.get("/listing/{lid}")
def listing(lid: int):
    return db.one("""SELECT id, type, deal, title, city, district, subdistrict, street, price_usd, price_gel,
        area_m2, usd_per_m2, rooms, floor, floors_total, is_project, furniture, near_subway,
        strftime(created, '%Y-%m-%d %H:%M') created, url, coord_precision FROM listings WHERE id = ?""", [lid])
