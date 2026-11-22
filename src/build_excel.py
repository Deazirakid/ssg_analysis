"""Build output/ss_ge_real_estate_dashboard.xlsx from data/clean/listings_all.csv."""
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "ss_ge_real_estate_dashboard.xlsx"

# palette (dataviz reference: blue sequential, orange as 2nd hue)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SEQ_LO, SEQ_MID, SEQ_HI = "#cde2fb", "#3987e5", "#0d366b"
GRID_STEP = 0.01  # ~1.1km x 0.8km cells for the Excel grid heatmap


def q(s, p):
    s = s.dropna()
    return float(np.percentile(s, p)) if len(s) else np.nan


def agg_prices(g, price="price_usd"):
    return pd.Series({
        "listings": len(g),
        "median_price_usd": g[price].median(),
        "median_usd_m2": g["usd_per_m2"].median(),
        "p25_usd_m2": q(g["usd_per_m2"], 25),
        "p75_usd_m2": q(g["usd_per_m2"], 75),
        "median_area_m2": g["area_m2"].median(),
    })


def main():
    df = pd.read_csv(ROOT / "data/clean/listings_all.csv", low_memory=False,
                     parse_dates=["created", "ordered"])
    quality = json.loads((ROOT / "data/clean/quality.json").read_text(encoding="utf-8"))
    run = quality["run"]
    meta_p = ROOT / "data/raw" / run / "meta.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}

    c = df[df["is_clean"]].copy()
    tb = c[c["is_tbilisi"]]
    apt_sale = tb[(tb["type"] == "Apartment") & (tb["deal"] == "Sale")]
    apt_rent = tb[(tb["type"] == "Apartment") & (tb["deal"] == "Rent")]

    # ---------- aggregates ----------
    d_sale = apt_sale.groupby("district").apply(agg_prices, include_groups=False)
    d_rent = apt_rent.groupby("district").agg(rent_listings=("id", "size"),
                                              median_rent_usd=("price_usd", "median"),
                                              median_rent_usd_m2=("usd_per_m2", "median"))
    dist = d_sale.join(d_rent, how="outer")
    dist["gross_yield_pct"] = (dist["median_rent_usd_m2"] * 12 / dist["median_usd_m2"] * 100).round(2)
    dist = dist[dist["listings"].fillna(0) >= 20].sort_values("median_usd_m2", ascending=False)
    dist = dist.reset_index().round(1)

    # neighbourhood level (subdistrict) - apartments, Tbilisi
    s_sale = apt_sale.groupby("subdistrict").apply(agg_prices, include_groups=False)
    s_rent = apt_rent.groupby("subdistrict").agg(rent_listings=("id", "size"),
                                                 median_rent_usd=("price_usd", "median"),
                                                 median_rent_usd_m2=("usd_per_m2", "median"))
    hood = s_sale.join(s_rent, how="left")
    hood["gross_yield_pct"] = (hood["median_rent_usd_m2"] * 12 / hood["median_usd_m2"] * 100).round(2)
    hood = hood[hood["listings"] >= 30].sort_values("median_usd_m2", ascending=False).reset_index().round(1)
    top = hood.sort_values("listings", ascending=False).head(25).sort_values(
        "median_usd_m2", ascending=False).reset_index(drop=True)

    sub = (tb.groupby(["type", "deal", "district", "subdistrict"])
             .apply(agg_prices, include_groups=False).reset_index())
    sub = sub[sub["listings"] >= 5].sort_values(["type", "deal", "median_usd_m2"],
                                                ascending=[True, True, False]).round(1)

    rooms = (apt_sale[apt_sale["rooms"].between(1, 6)].groupby("rooms")
             .apply(agg_prices, include_groups=False).reset_index().round(1))
    rooms["rooms"] = rooms["rooms"].astype(int).astype(str) + " room"

    proj = apt_sale.groupby(apt_sale["is_project"].map({True: "New build / project", False: "Resale"})) \
        .apply(agg_prices, include_groups=False).reset_index().rename(columns={"is_project": "segment"}).round(1)

    overview = c.pivot_table(index="type", columns="deal", values="id", aggfunc="count", fill_value=0)
    overview["Total"] = overview.sum(axis=1)
    overview = overview.sort_values("Total", ascending=False).reset_index()

    cities = (c.assign(place=c["city"].fillna(c["municipality"]))
               .groupby("place").agg(listings=("id", "size"),
                                     apt_sale_median_usd_m2=("usd_per_m2",
                                         lambda s: s[(c.loc[s.index, "type"] == "Apartment") &
                                                     (c.loc[s.index, "deal"] == "Sale")].median()))
               .sort_values("listings", ascending=False).head(25).reset_index().round(0))

    since = pd.Timestamp.now().normalize() - pd.Timedelta(days=60)
    daily = (c[c["created"] >= since].groupby(c["created"].dt.date)
             .agg(new_listings=("id", "size")).reset_index().rename(columns={"created": "date"}))
    daily_apt = (apt_sale[apt_sale["created"] >= since].groupby(apt_sale["created"].dt.date)
                 ["usd_per_m2"].median().rename("tbilisi_apt_sale_median_usd_m2"))
    daily = daily.merge(daily_apt, left_on="date", right_index=True, how="left").round(0)

    bins = list(range(0, 4001, 200)) + [np.inf]
    labels = [f"{b}-{b+200}" for b in range(0, 4000, 200)] + ["4000+"]
    hist = (pd.cut(apt_sale["usd_per_m2"], bins=bins, labels=labels, right=False)
            .value_counts().reindex(labels).fillna(0).astype(int).reset_index())
    hist.columns = ["usd_per_m2_band", "listings"]

    # grid heatmap (Tbilisi apartments for sale, median $/m2 per cell)
    g = apt_sale.dropna(subset=["lat", "lon", "usd_per_m2"])
    g = g[~g["flag_generic_pin"] & g["coord_precision"].isin(["exact", "street"])]
    g = g.assign(glat=(np.floor(g["lat"] / GRID_STEP) * GRID_STEP).round(3),
                 glon=(np.floor(g["lon"] / GRID_STEP) * GRID_STEP).round(3))
    cell = g.groupby(["glat", "glon"]).agg(n=("id", "size"), med=("usd_per_m2", "median"))
    cell = cell[cell["n"] >= 3]
    cell = cell[(cell.index.get_level_values("glat").to_series().between(41.60, 41.87).values)
                & (cell.index.get_level_values("glon").to_series().between(44.62, 45.05).values)]
    lats = np.round(np.arange(cell.index.get_level_values("glat").max(),
                              cell.index.get_level_values("glat").min() - 1e-9, -GRID_STEP), 3)
    lons = np.round(np.arange(cell.index.get_level_values("glon").min(),
                              cell.index.get_level_values("glon").max() + 1e-9, GRID_STEP), 3)
    heat = cell["med"].unstack("glon").reindex(index=lats, columns=lons)
    heat_n = cell["n"].unstack("glon").reindex(index=lats, columns=lons)

    flags = {k: v for k, v in quality.items() if k.startswith("flag_")}

    # ---------- workbook ----------
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT, engine="xlsxwriter",
                        engine_kwargs={"options": {"nan_inf_to_errors": True,
                                                   "strings_to_urls": False}}) as xw:
        wb = xw.book
        ws = wb.add_worksheet("Dashboard")  # first tab
        F = {
            "title": wb.add_format({"bold": True, "font_size": 20, "font_color": INK}),
            "sub": wb.add_format({"font_size": 10, "font_color": INK2}),
            "kpi_v": wb.add_format({"bold": True, "font_size": 22, "font_color": INK, "align": "left",
                                    "bg_color": "#f3f6fb", "top": 1, "left": 1, "right": 1,
                                    "border_color": GRID, "num_format": "#,##0"}),
            "kpi_l": wb.add_format({"font_size": 9, "font_color": INK2, "bg_color": "#f3f6fb",
                                    "bottom": 1, "left": 1, "right": 1, "border_color": GRID,
                                    "text_wrap": True, "valign": "top"}),
            "h": wb.add_format({"bold": True, "font_size": 12, "font_color": INK}),
            "hdr": wb.add_format({"bold": True, "bg_color": "#eef1f6", "border": 1,
                                  "border_color": GRID, "text_wrap": True, "valign": "top"}),
            "num": wb.add_format({"num_format": "#,##0"}),
            "num1": wb.add_format({"num_format": "#,##0.0"}),
            "pct": wb.add_format({"num_format": "0.00"}),
            "date": wb.add_format({"num_format": "yyyy-mm-dd"}),
            "dt": wb.add_format({"num_format": "yyyy-mm-dd hh:mm"}),
            "cell": wb.add_format({"num_format": "#,##0", "font_size": 8, "align": "center",
                                   "border": 1, "border_color": "#ffffff"}),
            "axis": wb.add_format({"font_size": 8, "font_color": INK2, "num_format": "0.00",
                                   "align": "center"}),
            "wrap": wb.add_format({"text_wrap": True, "valign": "top", "font_color": INK2}),
        }

        def table(sheet, frame, startrow=0, startcol=0, widths=None, name=None):
            frame.to_excel(xw, sheet_name=sheet, startrow=startrow, startcol=startcol, index=False)
            ws = xw.sheets[sheet]
            nr, nc = frame.shape
            ws.add_table(startrow, startcol, startrow + max(nr, 1), startcol + nc - 1, {
                "columns": [{"header": str(h)} for h in frame.columns],
                "style": "Table Style Light 9", "name": name,
            })
            for i, col in enumerate(frame.columns):
                w = (widths or {}).get(col, max(10, min(40, len(str(col)) + 2)))
                fmt = None
                if pd.api.types.is_float_dtype(frame[col]):
                    fmt = F["num1"] if "pct" not in col else F["pct"]
                elif pd.api.types.is_integer_dtype(frame[col]):
                    fmt = F["num"]
                ws.set_column(startcol + i, startcol + i, w, fmt)
            return ws

        def bar(sheet, nrows, cat_col, val_col, title, color=BLUE, horiz=True, startrow=0,
                y_title=None, num_fmt="#,##0"):
            ch = wb.add_chart({"type": "bar" if horiz else "column"})
            ch.add_series({
                "name": title,
                "categories": [sheet, startrow + 1, cat_col, startrow + nrows, cat_col],
                "values": [sheet, startrow + 1, val_col, startrow + nrows, val_col],
                "fill": {"color": color}, "border": {"none": True}, "gap": 60,
                "data_labels": {"value": True, "num_format": num_fmt,
                                "font": {"size": 8, "color": INK2}},
            })
            ch.set_title({"name": title, "name_font": {"size": 11, "bold": True, "color": INK}})
            ch.set_legend({"none": True})
            axis_font = {"size": 8, "color": INK2}
            ch.set_x_axis({"num_font": axis_font, "line": {"color": GRID},
                           **({"min": 0, "num_format": "#,##0"} if horiz else {}),
                           "major_gridlines": {"visible": horiz, "line": {"color": GRID}},
                           "reverse": False})
            ch.set_y_axis({"num_font": axis_font, "line": {"color": GRID}, "reverse": horiz,
                           **({} if horiz else {"min": 0, "num_format": "#,##0"}),
                           "major_gridlines": {"visible": not horiz, "line": {"color": GRID}},
                           "name": y_title, "name_font": {"size": 8, "color": INK2}})
            ch.set_chartarea({"border": {"none": True}, "fill": {"color": "#ffffff"}})
            ch.set_plotarea({"fill": {"color": "#ffffff"}})
            return ch

        # --- data sheets first (charts reference them) ---
        table("District_Stats", dist, name="DistrictStats", widths={"district": 26})
        table("Neighbourhoods", hood, name="Neighbourhoods", widths={"subdistrict": 26})
        xw.sheets["Neighbourhoods"].freeze_panes(1, 1)
        kk = hood.columns.get_loc("median_usd_m2")
        xw.sheets["Neighbourhoods"].conditional_format(1, kk, len(hood), kk, {
            "type": "3_color_scale", "min_color": SEQ_LO, "mid_color": SEQ_MID, "max_color": SEQ_HI})
        top.to_excel(xw, sheet_name="Chart_Top", index=False)
        top_y = top.sort_values("gross_yield_pct", ascending=False)[["subdistrict", "gross_yield_pct"]]
        top_r = top.sort_values("median_rent_usd", ascending=False)[["subdistrict", "median_rent_usd"]]
        top_n = top.sort_values("listings", ascending=False)[["subdistrict", "listings"]]
        top_y.to_excel(xw, sheet_name="Chart_Top", startcol=20, index=False)
        top_r.to_excel(xw, sheet_name="Chart_Top", startcol=23, index=False)
        top_n.to_excel(xw, sheet_name="Chart_Top", startcol=26, index=False)
        xw.sheets["Chart_Top"].hide()
        table("Subdistrict_Stats", sub, name="SubdistrictStats",
              widths={"district": 24, "subdistrict": 28, "type": 13, "deal": 11})
        ws_sub = xw.sheets["Subdistrict_Stats"]
        if len(sub):
            k = sub.columns.get_loc("median_usd_m2")
            ws_sub.conditional_format(1, k, len(sub), k, {"type": "3_color_scale", "min_color": SEQ_LO,
                                                         "mid_color": SEQ_MID, "max_color": SEQ_HI})
        ws_sub.freeze_panes(1, 0)

        # chart data sheet
        cd = "Chart_Data"
        r = 0
        blocks = {}
        for key, frame in [("rooms", rooms), ("proj", proj), ("daily", daily), ("hist", hist),
                           ("overview", overview), ("cities", cities)]:
            xw.sheets.get(cd)  # noqa
            frame.to_excel(xw, sheet_name=cd, startrow=r, index=False)
            blocks[key] = (r, len(frame))
            r += len(frame) + 3
        ws_cd = xw.sheets[cd]
        ws_cd.set_column(0, 0, 22, F["date"])
        ws_cd.set_column(1, 8, 16, F["num"])

        # grid heatmap sheet
        hs = "Heatmap_Grid"
        ws_h = wb.add_worksheet(hs)
        ws_h.write(0, 0, "Tbilisi apartments for sale: median USD per m² per ~1 km grid cell "
                         "(cells with 3+ listings). Rows = latitude (north at top), columns = longitude.",
                   F["h"])
        ws_h.write(1, 0, "Darker = more expensive. Hover a cell's comment for listing count.", F["sub"])
        if heat.size:
            for j, lon in enumerate(heat.columns):
                ws_h.write_number(3, j + 1, float(lon), F["axis"])
            for i, lat in enumerate(heat.index):
                ws_h.write_number(4 + i, 0, float(lat), F["axis"])
                for j, lon in enumerate(heat.columns):
                    v = heat.iat[i, j]
                    if pd.notna(v):
                        ws_h.write_number(4 + i, j + 1, float(v), F["cell"])
                        ws_h.write_comment(4 + i, j + 1, f"{int(heat_n.iat[i, j])} listings\n"
                                           f"lat {lat:.2f} lon {lon:.2f}",
                                           {"x_scale": 0.8, "y_scale": 0.4})
            ws_h.conditional_format(4, 1, 3 + len(heat.index), len(heat.columns), {
                "type": "3_color_scale", "min_color": SEQ_LO, "mid_color": SEQ_MID,
                "max_color": SEQ_HI, "min_type": "percentile", "min_value": 2,
                "mid_type": "percentile", "mid_value": 50, "max_type": "percentile", "max_value": 98})
            vals = heat.values[~np.isnan(heat.values)]
            ws_h.conditional_format(4, 1, 3 + len(heat.index), len(heat.columns), {
                "type": "cell", "criteria": ">=", "value": float(np.percentile(vals, 55)),
                "format": wb.add_format({"font_color": "#ffffff"})})
            ws_h.set_column(0, 0, 7)
            ws_h.set_column(1, len(heat.columns), 5.2)
            ws_h.set_default_row(18)
            ws_h.freeze_panes(4, 1)

        # listings sheet
        lst_cols = ["id", "type", "deal", "title", "is_tbilisi", "city", "district", "subdistrict",
                    "street", "lat", "lon", "price_usd", "price_gel", "area_m2", "usd_per_m2", "rooms",
                    "bedrooms", "floor", "floors_total", "is_project", "furniture", "near_subway",
                    "created", "age_days", "url"]
        L = c[lst_cols].sort_values("created", ascending=False)
        L.to_excel(xw, sheet_name="Listings", index=False)
        ws_l = xw.sheets["Listings"]
        ws_l.add_table(0, 0, len(L), len(lst_cols) - 1, {
            "columns": [{"header": h} for h in lst_cols], "style": "Table Style Light 9",
            "name": "Listings"})
        widths = {"title": 38, "district": 22, "subdistrict": 22, "street": 22, "url": 50,
                  "created": 16, "near_subway": 18}
        for i, col in enumerate(lst_cols):
            fmt = F["dt"] if col == "created" else F["num"] if col in (
                "price_usd", "price_gel", "usd_per_m2", "id") else None
            ws_l.set_column(i, i, widths.get(col, 11), fmt)
        ws_l.freeze_panes(1, 2)

        # market overview + quality
        table("Market_Overview", overview, name="Overview", widths={"type": 16})
        ws_o = xw.sheets["Market_Overview"]
        ws_o.write(len(overview) + 3, 0, "Top places (all Georgia)", F["h"])
        table("Market_Overview", cities, startrow=len(overview) + 4, name="Cities",
              widths={"place": 24})

        dq = pd.DataFrame(
            [("Run", run), ("Scraped at", meta.get("finished", "")), ("Scrape seconds", meta.get("seconds", "")),
             ("Threads", meta.get("workers", "")), ("HTTP requests", (meta.get("http") or {}).get("req", "")),
             ("Raw listings (merged)", quality["total"]), ("Clean listings", quality["clean"]),
             ("Clean Tbilisi listings", quality["tbilisi_clean"])]
            + [(f"Flag: {k[5:]}", v) for k, v in flags.items()]
            + [(f"Source: {k}", v) for k, v in quality["source"].items()],
            columns=["metric", "value"])
        dq["value"] = dq["value"].astype(str)
        table("Data_Quality", dq, name="Quality", widths={"metric": 30, "value": 28})
        ws_q = xw.sheets["Data_Quality"]
        notes = [
            "Definitions",
            "clean = has price, coords inside Georgia, not a price outlier, not a probable repost.",
            "outlier = |robust z| > 3.5 on log(USD/m²) within property type x deal, plus sanity bounds "
            "(apartment sale 150-12,000 $/m², apartment rent 80-25,000 $/month, apartment area 10-1,500 m²).",
            "duplicate = same type, deal, price, area, floor, subdistrict and street; newest kept.",
            "generic_pin = 25+ listings on the exact same coordinate (default pin); kept in tables, "
            "excluded from the grid heatmap.",
            "Rent prices are monthly USD; daily-rent prices are per night. Pledge = 'gíravdeba' (pledge/lease-back).",
            "gross_yield_pct = median rent USD/m² x 12 / median sale USD/m² for the district (apartments).",
            "Personal data (phones, names, descriptions, user IDs) is intentionally not stored.",
        ]
        for i, t in enumerate(notes):
            ws_q.write(len(dq) + 3 + i, 0, t, F["h"] if i == 0 else F["wrap"])

        # --- Dashboard ---
        ws.hide_gridlines(2)
        ws.set_column(0, 0, 2)
        ws.set_column(1, 24, 9.5)
        ws.write(0, 1, "ss.ge Real Estate Market — Tbilisi focus", F["title"])
        ws.write(1, 1, f"Source: home.ss.ge public listings · scraped {meta.get('finished', run)} · "
                       f"{quality['clean']:,} clean listings across Georgia", F["sub"])

        last7 = c[c["created"] >= pd.Timestamp.now() - pd.Timedelta(days=7)]
        kpis = [
            (len(c), "Clean listings, all Georgia"),
            (len(apt_sale), "Tbilisi apartments for sale"),
            (apt_sale["usd_per_m2"].median(), "Median USD / m², Tbilisi apt sale"),
            (apt_sale["price_usd"].median(), "Median price USD, Tbilisi apt sale"),
            (apt_rent["price_usd"].median(), "Median monthly rent USD, Tbilisi apt"),
            (len(last7), "New listings, last 7 days"),
        ]
        for i, (v, lab) in enumerate(kpis):
            col = 1 + i * 4
            ws.merge_range(3, col, 3, col + 2, float(v) if pd.notna(v) else 0, F["kpi_v"])
            ws.merge_range(4, col, 4, col + 2, lab, F["kpi_l"])
        ws.set_row(3, 34)
        ws.set_row(4, 28)

        nt = len(top)
        size = {"x_scale": 1.45, "y_scale": 2.3}
        if nt:
            ct = "Chart_Top"
            ch = bar(ct, nt, 0, top.columns.get_loc("median_usd_m2"),
                     "Median USD per m² — 25 biggest Tbilisi neighbourhoods, apartments for sale", BLUE)
            ws.insert_chart(6, 1, ch, size)
            ch = bar(ct, nt, 23, 24, "Median monthly rent (USD) — same neighbourhoods, apartments", ORANGE)
            ws.insert_chart(6, 13, ch, size)
            ch = bar(ct, nt, 20, 21, "Gross rental yield % (rent×12 / sale price, per m²)", AQUA,
                     num_fmt="0.0")
            ws.insert_chart(42, 1, ch, size)
            ch = bar(ct, nt, 26, 27, "Apartments for sale — listing count by neighbourhood", BLUE)
            ws.insert_chart(42, 13, ch, size)

        r0, n = blocks["daily"]
        if n:
            ch = wb.add_chart({"type": "line"})
            ch.add_series({"name": "New listings per day",
                           "categories": [cd, r0 + 1, 0, r0 + n, 0],
                           "values": [cd, r0 + 1, 1, r0 + n, 1],
                           "line": {"color": BLUE, "width": 2}})
            ch.set_title({"name": "New listings per day (all Georgia, last 60 days)",
                          "name_font": {"size": 11, "bold": True}})
            ch.set_legend({"none": True})
            ch.set_x_axis({"date_axis": True, "num_format": "dd mmm", "num_font": {"size": 8, "color": INK2},
                           "line": {"color": GRID}})
            ch.set_y_axis({"num_font": {"size": 8, "color": INK2}, "major_gridlines":
                           {"visible": True, "line": {"color": GRID}}, "line": {"none": True}})
            ch.set_chartarea({"border": {"none": True}})
            ws.insert_chart(78, 1, ch, {"x_scale": 1.45, "y_scale": 1.1})
            ch = wb.add_chart({"type": "line"})
            ch.add_series({"name": "Median USD/m² of new Tbilisi apartment-sale listings",
                           "categories": [cd, r0 + 1, 0, r0 + n, 0],
                           "values": [cd, r0 + 1, 2, r0 + n, 2],
                           "line": {"color": BLUE, "width": 2}})
            ch.set_title({"name": "Asking USD/m² of new listings by day (Tbilisi apt sale)",
                          "name_font": {"size": 11, "bold": True}})
            ch.set_legend({"none": True})
            ch.set_x_axis({"date_axis": True, "num_format": "dd mmm", "num_font": {"size": 8, "color": INK2},
                           "line": {"color": GRID}})
            ch.set_y_axis({"num_font": {"size": 8, "color": INK2}, "major_gridlines":
                           {"visible": True, "line": {"color": GRID}}, "line": {"none": True}})
            ch.set_chartarea({"border": {"none": True}})
            ws.insert_chart(78, 13, ch, {"x_scale": 1.45, "y_scale": 1.1})

        r0, n = blocks["hist"]
        ch = bar(cd, n, 0, 1, "Price distribution — Tbilisi apt sale, listings per USD/m² band", BLUE,
                 horiz=False, startrow=r0)
        ws.insert_chart(96, 1, ch, {"x_scale": 1.45, "y_scale": 1.2})
        r0, n = blocks["rooms"]
        ch = bar(cd, n, 0, 3, "Median USD/m² by room count — Tbilisi apt sale", BLUE, horiz=False,
                 startrow=r0)
        ws.insert_chart(96, 13, ch, {"x_scale": 0.72, "y_scale": 1.2})
        r0, n = blocks["proj"]
        ch = bar(cd, n, 0, 3, "Median USD/m²: new build vs resale", BLUE, horiz=False, startrow=r0)
        ws.insert_chart(96, 19, ch, {"x_scale": 0.72, "y_scale": 1.2})

        r0, n = blocks["overview"]
        ocols = list(overview.columns)
        ch = bar(cd, n, 0, ocols.index("Total"), "Active listings by property type (all deals, Georgia)",
                 BLUE, startrow=r0)
        ws.insert_chart(114, 1, ch, {"x_scale": 1.45, "y_scale": 1.1})
        r0, n = blocks["cities"]
        ch = bar(cd, min(n, 15), 0, 1, "Top 15 places by listing count", BLUE, startrow=r0)
        ws.insert_chart(114, 13, ch, {"x_scale": 1.45, "y_scale": 1.1})

        ws.write(132, 1, "Sheets: Neighbourhoods · District_Stats · Subdistrict_Stats · Heatmap_Grid · Listings "
                         "(filterable, clean rows) · Market_Overview · Data_Quality. "
                         "Interactive map: output/heatmap.html", F["sub"])
        ws.activate()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
