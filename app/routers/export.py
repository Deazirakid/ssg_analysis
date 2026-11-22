"""Exports: filtered listings as XLSX (opens in Excel / uploads to Google Sheets)
and a Sheets-friendly CSV feed for =IMPORTDATA() using an API key."""
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from .. import db
from ..auth import require_user
from ..db import Filters, filters_dep
from .listings import COLS, export_csv

router = APIRouter(prefix="/api/export", tags=["export"], dependencies=[Depends(require_user)])


@router.get("/listings.xlsx", summary="Filtered listings as an Excel workbook (Listings + Summary sheets)")
def xlsx(f: Filters = Depends(filters_dep)):
    import pandas as pd
    w, p = f.where()
    df = db.cur().execute(f"SELECT {','.join(COLS)} FROM listings WHERE {w} ORDER BY created DESC LIMIT 200000", p).df()
    summ = db.cur().execute(f"""SELECT subdistrict, count(*) listings, round(median(price_usd)) median_price_usd,
        round(median(usd_per_m2)) median_usd_m2, round(median(area_m2)) median_area FROM listings WHERE {w}
        GROUP BY 1 ORDER BY listings DESC""", p).df()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_urls": False}}) as xw:
        for name, frame in (("Listings", df), ("Summary", summ)):
            frame.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            ws.add_table(0, 0, max(len(frame), 1), len(frame.columns) - 1,
                         {"columns": [{"header": c} for c in frame.columns], "style": "Table Style Light 9"})
            ws.freeze_panes(1, 0)
            ws.set_column(0, len(frame.columns) - 1, 14)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=ss_ge_listings.xlsx"})


@router.get("/sheets.csv", summary="CSV feed for Google Sheets: =IMPORTDATA(\"https://HOST/api/export/sheets.csv?api_key=KEY&...filters\")")
def sheets_csv(f: Filters = Depends(filters_dep)):
    return export_csv(f)
