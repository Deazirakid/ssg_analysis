"""Push data/app/listings.parquet into MariaDB (DATABASE_URL in .env).

Tables
  listings       current snapshot (replaced atomically each run via swap)
  price_history  (id, run, price_usd, usd_per_m2) appended per run -> price-change tracking
  scrape_runs    one row per run with quality stats
  auth_log       created here, written by the web app
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DDL_LISTINGS = """
CREATE TABLE {name} (
  id BIGINT PRIMARY KEY,
  type VARCHAR(32), deal VARCHAR(32), title VARCHAR(255),
  is_tbilisi TINYINT(1), city VARCHAR(96), district VARCHAR(96), subdistrict VARCHAR(96),
  street VARCHAR(160), lat DOUBLE, lon DOUBLE, coord_precision VARCHAR(16),
  price_usd DOUBLE, price_gel DOUBLE, area_m2 DOUBLE, usd_per_m2 DOUBLE,
  rooms SMALLINT, bedrooms SMALLINT, floor SMALLINT, floors_total SMALLINT,
  is_project TINYINT(1), furniture TINYINT(1), near_subway VARCHAR(160),
  images SMALLINT, vip_status SMALLINT, is_urgent TINYINT(1), created DATETIME,
  url VARCHAR(400), flag_generic_pin TINYINT(1),
  home_id BIGINT, poster CHAR(12), dist_center_km DOUBLE, metro_km DOUBLE, metro_name VARCHAR(40),
  price_z DOUBLE, ordered DATETIME, run VARCHAR(16),
  KEY ix_poster (poster), KEY ix_home (home_id),
  KEY ix_type_deal (type, deal), KEY ix_sub (subdistrict), KEY ix_created (created)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

DDL_OTHER = [
    """CREATE TABLE IF NOT EXISTS price_history (
         id BIGINT NOT NULL, run VARCHAR(16) NOT NULL, price_usd DOUBLE, usd_per_m2 DOUBLE,
         PRIMARY KEY (id, run), KEY ix_run (run)
       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS scrape_runs (
         run VARCHAR(16) PRIMARY KEY, loaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
         listings INT, quality JSON
       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS auth_log (
         id BIGINT AUTO_INCREMENT PRIMARY KEY, ts DATETIME DEFAULT CURRENT_TIMESTAMP,
         event VARCHAR(24), username VARCHAR(64), ip VARCHAR(64), user_agent VARCHAR(255),
         KEY ix_ts (ts)
       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL missing in .env")
    df = pd.read_parquet(ROOT / "data/app/listings.parquet")
    q = json.loads((ROOT / "data/app/quality.json").read_text(encoding="utf-8"))
    run = q["run"]
    df["run"] = run
    df["title"] = df["title"].astype("string").str.slice(0, 255)
    df["street"] = df["street"].astype("string").str.slice(0, 160)
    df["near_subway"] = df["near_subway"].astype("string").str.slice(0, 160)
    df = df.astype(object).where(df.notna(), None)

    eng = create_engine(url, pool_pre_ping=True)
    with eng.begin() as c:
        for ddl in DDL_OTHER:
            c.execute(text(ddl))
        c.execute(text("DROP TABLE IF EXISTS listings_new"))
        c.execute(text(DDL_LISTINGS.format(name="listings_new")))

    cols = list(df.columns)
    ins = f"INSERT INTO listings_new ({','.join('`'+c+'`' for c in cols)}) VALUES ({','.join(['%s']*len(cols))})"
    data = [tuple(r) for r in df.itertuples(index=False, name=None)]
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        for i in range(0, len(data), 5000):
            cur.executemany(ins, data[i:i + 5000])
            print(f"  listings {min(i + 5000, len(data))}/{len(data)}", flush=True)
        # duplicate clusters -> table
        dup = pd.read_parquet(ROOT / "data/app/duplicates.parquet")
        dup = dup.astype(object).where(dup.notna(), None)
        cur.execute("DROP TABLE IF EXISTS duplicates")
        cur.execute("""CREATE TABLE duplicates (type VARCHAR(32), deal VARCHAR(32), price_usd DOUBLE,
            area_m2 DOUBLE, floor DOUBLE, subdistrict VARCHAR(96), street VARCHAR(160), title VARCHAR(255),
            n INT, posters INT, ids TEXT) DEFAULT CHARSET=utf8mb4""")
        dcols = list(dup.columns)
        cur.executemany(f"INSERT INTO duplicates ({','.join(dcols)}) VALUES ({','.join(['%s']*len(dcols))})",
                        [tuple(r) for r in dup.itertuples(index=False, name=None)])
        hist = [(r[0], run, r[1], r[2]) for r in df[["id", "price_usd", "usd_per_m2"]].itertuples(index=False, name=None)]
        for i in range(0, len(hist), 10000):
            cur.executemany("INSERT IGNORE INTO price_history (id, run, price_usd, usd_per_m2) VALUES (%s,%s,%s,%s)",
                            hist[i:i + 10000])
        cur.execute("REPLACE INTO scrape_runs (run, listings, quality) VALUES (%s,%s,%s)",
                    (run, len(df), json.dumps(q, ensure_ascii=False)))
        # atomic swap so the app never sees a half-loaded table
        cur.execute("CREATE TABLE IF NOT EXISTS listings LIKE listings_new")
        cur.execute("RENAME TABLE listings TO listings_old, listings_new TO listings")
        cur.execute("DROP TABLE listings_old")
        raw.commit()
    finally:
        raw.close()
    print(f"loaded {len(df)} listings into MySQL (run {run})")


if __name__ == "__main__":
    main()
