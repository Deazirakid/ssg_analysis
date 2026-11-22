import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from .. import db
from ..auth import require_user
from ..db import Filters, filters_dep

router = APIRouter(prefix="/api/listings", tags=["listings"], dependencies=[Depends(require_user)])

COLS = ["id", "type", "deal", "title", "city", "district", "subdistrict", "street", "price_usd",
        "usd_per_m2", "area_m2", "rooms", "floor", "floors_total", "is_project", "furniture",
        "near_subway", "created", "url"]
SORTABLE = {"price_usd", "usd_per_m2", "area_m2", "rooms", "floor", "created", "id", "subdistrict"}


@router.get("")
def list_listings(f: Filters = Depends(filters_dep), page: int = 1, size: int = 50,
                  sort: str = "created", dir: str = "desc"):
    size = min(max(size, 10), 200)
    sort = sort if sort in SORTABLE else "created"
    d = "ASC" if dir.lower() == "asc" else "DESC"
    w, p = f.where()
    total = db.one(f"SELECT count(*) n FROM listings WHERE {w}", p)["n"]
    rows = db.rows(f"""SELECT {','.join(COLS)} FROM listings WHERE {w}
        ORDER BY {sort} {d} NULLS LAST, id LIMIT ? OFFSET ?""", p + [size, (max(page, 1) - 1) * size])
    for r in rows:
        r["created"] = str(r["created"])[:16] if r["created"] else None
    return {"total": total, "page": page, "size": size, "rows": rows}


@router.get(".csv")
def export_csv(f: Filters = Depends(filters_dep)):
    w, p = f.where()
    c = db.cur()
    res = c.execute(f"SELECT {','.join(COLS)} FROM listings WHERE {w} ORDER BY created DESC LIMIT 200000", p)

    def gen():
        buf = io.StringIO()
        wr = csv.writer(buf)
        buf.write("﻿")
        wr.writerow(COLS)
        while True:
            chunk = res.fetchmany(5000)
            if not chunk:
                break
            wr.writerows(chunk)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
        yield buf.getvalue()

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=ss_ge_listings.csv"})
