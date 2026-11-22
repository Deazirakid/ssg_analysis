"""Slim, typed parquet the web app serves: data/app/listings.parquet (+ quality.json copy)."""
import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLS = ["id", "type", "deal", "title", "is_tbilisi", "city", "municipality", "district", "subdistrict",
        "street", "lat", "lon", "coord_precision", "price_usd", "price_gel", "area_m2", "usd_per_m2",
        "rooms", "bedrooms", "floor", "floors_total", "is_project", "furniture", "near_subway",
        "images", "vip_status", "is_urgent", "created", "url", "flag_generic_pin",
        "home_id", "poster", "dist_center_km", "metro_km", "metro_name", "price_z", "ordered"]


def main():
    df = pd.read_parquet(ROOT / "data/clean/listings_all.parquet")
    allrows = df
    df = df[df["is_clean"]][COLS].copy()
    df["city"] = df["city"].fillna(df["municipality"])
    df = df.drop(columns="municipality")
    for c in ["is_tbilisi", "is_project", "furniture", "is_urgent", "flag_generic_pin"]:
        df[c] = df[c].fillna(False).astype(bool)
    for c in ["rooms", "bedrooms", "floor", "floors_total", "images", "vip_status"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").round().clip(-100, 30000).astype("Int16")
    df["created"] = pd.to_datetime(df["created"], errors="coerce")
    df["ordered"] = pd.to_datetime(df["ordered"], errors="coerce")
    df["home_id"] = pd.to_numeric(df["home_id"], errors="coerce").astype("Int64")
    for c in ["is_tbilisi"]:
        pass
    # metro distance is only meaningful inside Tbilisi
    df.loc[~df["is_tbilisi"], ["metro_km", "metro_name"]] = None
    out = ROOT / "data/app"
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "listings.parquet", index=False, compression="zstd")
    shutil.copy(ROOT / "data/clean/quality.json", out / "quality.json")

    # reposts / duplicate clusters across ALL feed rows (incl. the ones cleaning dropped)
    feed = allrows[allrows["source"] != "map only"]
    key = ["type", "deal", "price_usd", "area_m2", "floor", "street_id", "street_no"]
    d = feed[feed["area_m2"].notna() & feed["street_id"].notna()]
    g = (d.groupby(key, dropna=False).agg(n=("id", "size"), ids=("id", lambda s: ",".join(map(str, list(s)[:20]))),
                                         posters=("poster", "nunique"), subdistrict=("subdistrict", "first"),
                                         street=("street", "first"), title=("title", "first"))
         .reset_index())
    g = g[g["n"] >= 2].sort_values("n", ascending=False)
    g[["type", "deal", "price_usd", "area_m2", "floor", "subdistrict", "street", "title", "n", "posters", "ids"]]         .to_parquet(out / "duplicates.parquet", index=False)
    print("duplicate clusters:", len(g))
    print("wrote", out / "listings.parquet", len(df), "rows",
          f"{(out / 'listings.parquet').stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
