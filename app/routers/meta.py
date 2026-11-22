import json

from fastapi import APIRouter, Depends

from .. import db
from ..auth import require_user
from ..config import get_settings

router = APIRouter(prefix="/api", tags=["meta"], dependencies=[Depends(require_user)])


@router.get("/options")
def options():
    """Values for filter controls."""
    types = [r["type"] for r in db.rows("SELECT type, count(*) n FROM listings GROUP BY 1 ORDER BY n DESC")]
    deals = [r["deal"] for r in db.rows("SELECT deal, count(*) n FROM listings GROUP BY 1 ORDER BY n DESC")]
    tree = db.rows("""SELECT district, subdistrict, count(*) n FROM listings
                      WHERE is_tbilisi AND district IS NOT NULL AND subdistrict IS NOT NULL
                      GROUP BY 1,2 ORDER BY 1, n DESC""")
    districts: dict[str, list] = {}
    for r in tree:
        districts.setdefault(r["district"], []).append(r["subdistrict"])
    cities = [r["city"] for r in db.rows("""SELECT city, count(*) n FROM listings WHERE city IS NOT NULL
                                            GROUP BY 1 ORDER BY n DESC LIMIT 60""")]
    snap = db.one("SELECT max(created) latest, count(*) total FROM listings")
    return {"types": types, "deals": deals, "districts": districts, "cities": cities,
            "snapshot": str(snap["latest"])[:16], "total": snap["total"]}


@router.get("/quality")
def quality():
    s = get_settings()
    q = json.loads(s.quality_path.read_text(encoding="utf-8")) if s.quality_path.exists() else {}
    q["by_type_deal"] = db.rows("""SELECT type, deal, count(*) listings,
            round(median(price_usd)) median_price_usd, round(median(usd_per_m2)) median_usd_m2
            FROM listings GROUP BY 1,2 ORDER BY listings DESC""")
    q["precision"] = db.rows("SELECT coord_precision, count(*) n FROM listings GROUP BY 1 ORDER BY n DESC")
    return q


@router.get("/meta/metro", summary="Tbilisi metro stations (approximate coordinates)")
def metro():
    from ..geo_ref import METRO
    return [{"name": k, "lat": v[0], "lon": v[1]} for k, v in METRO.items()]
