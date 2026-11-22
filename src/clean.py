"""Merge MapSearch pins + LegendSearch listings -> clean dataset.

Output: data/clean/listings_all.csv      every listing + quality flags
        data/clean/listings_clean.csv    analysis-ready (valid, non-outlier, deduped)
        data/clean/listings.parquet      (if pyarrow present)
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from scrape import TYPES, DEALS  # noqa: E402

GEO_BBOX = (41.0, 43.7, 39.9, 46.8)        # Georgia lat/lon bounds
TBILISI_BBOX = (41.60, 41.87, 44.62, 45.05)
POSTER_SALT = os.environ.get("POSTER_SALT", "ssge-poster-v1")
CENTER = (41.6934, 44.8015)  # Freedom Square
# Tbilisi metro stations (approximate coordinates)
METRO = {
    "Akhmeteli Theatre": (41.8007, 44.7698), "Sarajishvili": (41.7930, 44.7728),
    "Guramishvili": (41.7841, 44.7883), "Grmagele": (41.7727, 44.7920), "Didube": (41.7556, 44.7844),
    "Gotsiridze": (41.7494, 44.7920), "Nadzaladevi": (41.7413, 44.7979), "Station Square": (41.7213, 44.7987),
    "Marjanishvili": (41.7106, 44.7926), "Rustaveli": (41.7025, 44.7924), "Freedom Square": (41.6934, 44.8015),
    "Avlabari": (41.6941, 44.8115), "300 Aragveli": (41.6879, 44.8216), "Isani": (41.6885, 44.8339),
    "Samgori": (41.6865, 44.8505), "Varketili": (41.6909, 44.8668), "Tsereteli": (41.7257, 44.7732),
    "Technical University": (41.7228, 44.7652), "Medical University": (41.7193, 44.7446),
    "Delisi": (41.7299, 44.7409), "Vazha-Pshavela": (41.7277, 44.7317), "State University": (41.7258, 44.7266),
}


def haversine_km(lat, lon, lat2, lon2):
    lat, lon, lat2, lon2 = map(np.radians, (lat, lon, lat2, lon2))
    a = np.sin((lat2 - lat) / 2) ** 2 + np.cos(lat) * np.cos(lat2) * np.sin((lon2 - lon) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


ROOMS_RX = re.compile(r"(\d+)\s*ოთახ")


def load_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def flatten_list(it):
    a = it.get("address") or {}
    p = it.get("price") or {}
    title = it.get("title") or ""
    m = ROOMS_RX.search(title)
    subway = it.get("nearbySubwayStations") or []
    return {
        "id": it["applicationId"],
        "type_id": it.get("type"), "deal_id": it.get("dealType"),
        "title": title,
        "city": a.get("cityTitle"), "city_id": a.get("cityId"),
        "municipality": a.get("municipalityTitle"),
        "district": a.get("districtTitle"), "district_id": a.get("districtId"),
        "subdistrict": a.get("subdistrictTitle"), "subdistrict_id": a.get("subdistrictId"),
        "street": a.get("streetTitle"), "street_no": a.get("streetNumber"),
        "street_id": a.get("streetId"),
        "price_usd_l": p.get("priceUsd"), "price_gel": p.get("priceGeo"),
        "usd_m2_site": p.get("unitPriceUsd"), "gel_m2_site": p.get("unitPriceGeo"),
        "area_m2": it.get("totalArea"),
        "rooms": int(m.group(1)) if m else None,
        "bedrooms": it.get("numberOfBedrooms"),
        "floor": it.get("floorNumber"), "floors_total": it.get("totalAmountOfFloor"),
        "furniture": it.get("furniture"), "built_in_kitchen": it.get("withBuiltInKitchen"),
        "images": it.get("imageCount"),
        "vip_status": it.get("vipStatus"), "is_urgent": it.get("isUrgent"),
        "is_exclusive": it.get("isExclusive"), "is_project": bool(it.get("homeId")),
        "home_id": it.get("homeId"),
        # pseudonymous poster id: salted hash, raw userId never stored
        "poster": hashlib.sha256((POSTER_SALT + str(it.get("userId"))).encode()).hexdigest()[:12]
                  if it.get("userId") else None,
        "near_subway": ", ".join(s.get("title", "") if isinstance(s, dict) else str(s) for s in subway) or None,
        "created": it.get("createDate"), "ordered": it.get("orderDate"),
        "url": "https://home.ss.ge/ka/udzravi-qoneba/" + (it.get("detailUrl") or str(it["applicationId"])),
    }


def flatten_map(it):
    p = it.get("price") or {}
    return {"id": it["applicationId"], "type_id_m": it["type"], "deal_id_m": it["dealType"],
            "lat": it.get("locationLatitude"), "lon": it.get("locationLongitude"),
            "price_usd_m": p.get("priceUsd"), "manual_pin": it.get("isManualPin")}


def robust_z(s):
    med = s.median()
    mad = (s - med).abs().median() * 1.4826
    return (s - med) / mad if mad and mad > 0 else s * 0


def main(run=None):
    run = run or (ROOT / "data/raw/LATEST").read_text().strip()
    raw = ROOT / "data/raw" / run
    L = pd.DataFrame(flatten_list(x) for x in load_jsonl(raw / "list.jsonl")) \
        if (raw / "list.jsonl").exists() else pd.DataFrame(columns=["id"])
    M = pd.DataFrame(flatten_map(x) for x in load_jsonl(raw / "map.jsonl")).drop_duplicates("id")
    L = L.drop_duplicates("id")

    df = M.merge(L, on="id", how="outer", indicator=True)
    df["source"] = df["_merge"].map({"both": "map+list", "left_only": "map only", "right_only": "list only"})
    df = df.drop(columns="_merge")
    df["type_id"] = df["type_id"].fillna(df["type_id_m"]).astype("Int64")
    df["deal_id"] = df["deal_id"].fillna(df["deal_id_m"]).astype("Int64")
    df["price_usd"] = df["price_usd_l"].fillna(df["price_usd_m"])
    df = df.drop(columns=["type_id_m", "deal_id_m", "price_usd_l", "price_usd_m"])
    df["type"] = df["type_id"].map(TYPES)
    df["deal"] = df["deal_id"].map(DEALS)

    # numeric cleanup
    for c in ["price_usd", "price_gel", "area_m2", "floors_total", "lat", "lon", "usd_m2_site", "bedrooms"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["floor"] = pd.to_numeric(df["floor"].astype(str).str.extract(r"(-?\d+)")[0], errors="coerce")
    df.loc[df["area_m2"] <= 0, "area_m2"] = np.nan
    df["usd_per_m2"] = (df["price_usd"] / df["area_m2"]).round(1)
    for c in ["created", "ordered"]:
        df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_convert("Asia/Tbilisi").dt.tz_localize(None)
    df["created_date"] = df["created"].dt.date
    df["age_days"] = (pd.Timestamp.now() - df["created"]).dt.days
    for c in ["title", "district", "subdistrict", "street", "city", "municipality"]:
        df[c] = df[c].astype("string").str.strip().replace({"": pd.NA})

    # ---- coordinate imputation for listings ss.ge has no pin for ----
    in_geo0 = df["lat"].between(GEO_BBOX[0], GEO_BBOX[1]) & df["lon"].between(GEO_BBOX[2], GEO_BBOX[3])
    df.loc[~in_geo0, ["lat", "lon"]] = np.nan
    df["coord_precision"] = np.where(df["lat"].notna(), "exact", None)
    pinned = df[df["lat"].notna()]
    for level, keys in [("street", ["city_id", "street_id"]),
                        ("subdistrict", ["city_id", "subdistrict_id"]),
                        ("district", ["city_id", "district_id"]),
                        ("city", ["city_id"])]:
        cent = pinned.dropna(subset=keys).groupby(keys).agg(
            _lat=("lat", "median"), _lon=("lon", "median"), _n=("id", "size"))
        cent = cent[cent["_n"] >= 3].reset_index()
        need = df["lat"].isna() & df[keys].notna().all(axis=1)
        if not need.any():
            continue
        fill = df.loc[need, ["id"] + keys].merge(cent, on=keys, how="left").set_index("id")
        idx = df.loc[need, "id"]
        lat = idx.map(fill["_lat"]); lon = idx.map(fill["_lon"])
        ok = lat.notna()
        df.loc[ok[ok].index, "lat"] = lat[ok]
        df.loc[ok[ok].index, "lon"] = lon[ok]
        df.loc[ok[ok].index, "coord_precision"] = level
    df["coord_precision"] = df["coord_precision"].fillna("none")

    # distances (Tbilisi only)
    tbm = df["lat"].notna()
    df["dist_center_km"] = np.where(tbm, haversine_km(df["lat"], df["lon"], *CENTER), np.nan).round(2)
    names = list(METRO)
    dm = np.vstack([haversine_km(df["lat"].values, df["lon"].values, *METRO[n]) for n in names])
    best = np.nanargmin(np.where(np.isnan(dm), np.inf, dm), axis=0)
    df["metro_km"] = np.where(tbm, dm[best, np.arange(len(df))], np.nan).round(2)
    df["metro_name"] = np.where(tbm, np.array(names, dtype=object)[best], None)

    # area label: Tbilisi listings get district, else city/municipality
    in_geo = df["lat"].between(GEO_BBOX[0], GEO_BBOX[1]) & df["lon"].between(GEO_BBOX[2], GEO_BBOX[3])
    in_tb = df["lat"].between(TBILISI_BBOX[0], TBILISI_BBOX[1]) & df["lon"].between(TBILISI_BBOX[2], TBILISI_BBOX[3])
    df["is_tbilisi"] = (df["city_id"] == 95) | (df["city_id"].isna() & in_tb)

    # ---- quality flags ----
    df["flag_no_price"] = ~(df["price_usd"] > 0)
    df["flag_bad_coords"] = ~in_geo
    ex = df["coord_precision"] == "exact"
    # default pin = one exact point reused by listings from many different subdistricts
    # (big buildings/projects share a pin too, but sit in a single subdistrict)
    grp = df[ex].groupby(["lat", "lon"])
    n_sub = grp["subdistrict_id"].transform("nunique")
    n = grp["id"].transform("count")
    df["flag_generic_pin"] = False
    df.loc[n.index, "flag_generic_pin"] = (n >= 10) & (n_sub >= 4)
    df["flag_no_area"] = df["area_m2"].isna() & df["type_id"].isin([4, 5, 6, 1])

    # outliers on log($/m2) within type x deal (fallback: log(price))
    feed = df["source"] != "map only"
    has_m2 = df["usd_per_m2"] > 0
    df["_m"] = np.where(has_m2, np.log(df["usd_per_m2"].where(has_m2)),
                        np.log(df["price_usd"].where(df["price_usd"] > 0)))
    df["_k"] = has_m2.map({True: "m2", False: "abs"})
    df["price_z"] = np.nan
    df.loc[feed, "price_z"] = (df[feed].groupby(["type_id", "deal_id", "_k"])["_m"]
                               .transform(robust_z).round(2))
    df["flag_outlier"] = df["price_z"].abs() > 3.5
    # hard sanity bounds for apartments
    apt_sale = (df["type_id"] == 5) & (df["deal_id"] == 4) & feed
    apt_rent = (df["type_id"] == 5) & (df["deal_id"] == 1) & feed
    df.loc[apt_sale & ~df["usd_per_m2"].between(150, 12000), "flag_outlier"] = True
    df.loc[apt_rent & ~df["price_usd"].between(80, 25000), "flag_outlier"] = True
    df.loc[(df["type_id"] == 5) & feed & ~df["area_m2"].between(10, 1500), "flag_outlier"] = True
    df = df.drop(columns=["_m", "_k"])

    # probable reposts: identical type/deal/price/area/floor/rooms on the same street + number
    key = ["type_id", "deal_id", "price_usd", "area_m2", "floor", "floors_total", "rooms",
           "city_id", "street_id", "street_no", "images"]
    df = df.sort_values("ordered", ascending=False, na_position="last")
    df["flag_duplicate"] = (df.duplicated(key, keep="first") & df["area_m2"].notna()
                            & df["street_id"].notna() & (df["source"] != "map only"))

    # map-only = pin not in the active listing feed (no attributes) -> not analysis-ready
    df["flag_not_in_feed"] = df["source"] == "map only"
    df["is_clean"] = ~(df["flag_no_price"] | df["flag_outlier"]
                       | df["flag_duplicate"] | df["flag_not_in_feed"])

    cols = ["id", "type", "deal", "title", "is_tbilisi", "city", "municipality", "district", "subdistrict",
            "street", "street_no", "lat", "lon", "coord_precision", "manual_pin", "price_usd", "price_gel", "area_m2",
            "usd_per_m2", "usd_m2_site", "rooms", "bedrooms", "floor", "floors_total", "furniture",
            "built_in_kitchen", "is_project", "near_subway", "images", "vip_status", "is_urgent",
            "is_exclusive", "created", "created_date", "ordered", "age_days", "url", "source",
            "price_z", "flag_no_price", "flag_bad_coords", "flag_generic_pin", "flag_no_area",
            "flag_outlier", "flag_duplicate", "flag_not_in_feed", "is_clean", "type_id", "deal_id", "city_id",
            "district_id", "subdistrict_id", "street_id", "home_id", "poster",
            "dist_center_km", "metro_km", "metro_name"]
    df = df[cols].sort_values(["type_id", "deal_id", "id"])

    out = ROOT / "data/clean"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "listings_all.csv", index=False, encoding="utf-8-sig")
    clean = df[df["is_clean"]]
    clean.to_csv(out / "listings_clean.csv", index=False, encoding="utf-8-sig")
    try:
        df.to_parquet(out / "listings_all.parquet", index=False)
    except Exception as e:
        print("parquet skipped:", e)

    fd = df[df["source"] != "map only"]
    q = {"run": run, "total": len(df), "clean": len(clean),
         **{c: int(fd[c].sum()) for c in df.columns if c.startswith("flag_") and c != "flag_not_in_feed"},
         "flag_not_in_feed": int(df["flag_not_in_feed"].sum()),
         "feed_listings": len(fd),
         "source": df["source"].value_counts().to_dict(),
         "tbilisi_clean": int(clean["is_tbilisi"].sum()),
         "coord_precision_clean": clean["coord_precision"].value_counts().to_dict()}
    (out / "quality.json").write_text(json.dumps(q, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(q, indent=1, ensure_ascii=False))
    return df


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
