"""DuckDB in-memory store + shared filter -> SQL WHERE builder."""
import logging
import threading
import time
from dataclasses import dataclass, field

import duckdb
from fastapi import Query

from .config import get_settings

_con: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()
log = logging.getLogger("db")


_engine = None
source_info: dict = {}


def engine():
    """SQLAlchemy engine for MariaDB (source of truth)."""
    global _engine
    s = get_settings()
    if _engine is None and s.database_url:
        from sqlalchemy import create_engine
        _engine = create_engine(s.database_url, pool_pre_ping=True, pool_recycle=1800, pool_size=5,
                                connect_args={"init_command": "SET time_zone = '+04:00'"})  # Tbilisi time
    return _engine


HISTORY_RUNS = 8


def _fetch_mysql():
    import pandas as pd
    t = time.time()
    with engine().connect() as c:
        df = pd.read_sql("SELECT * FROM listings", c)
        run = c.exec_driver_sql("SELECT max(run) FROM listings").scalar()
        runs = [r[0] for r in c.exec_driver_sql(
            f"SELECT DISTINCT run FROM price_history ORDER BY run DESC LIMIT {HISTORY_RUNS}")]
        hist = pd.read_sql(
            "SELECT id, run, price_usd, usd_per_m2 FROM price_history WHERE run IN ("
            + ",".join(f"'{r}'" for r in runs) + ")", c) if runs else pd.DataFrame(
            columns=["id", "run", "price_usd", "usd_per_m2"])
        try:
            dup = pd.read_sql("SELECT * FROM duplicates", c)
        except Exception:
            dup = pd.DataFrame()
    for col in ["is_tbilisi", "is_project", "furniture", "is_urgent", "flag_generic_pin"]:
        df[col] = df[col].fillna(0).astype(bool)
    df["created"] = pd.to_datetime(df["created"])
    return df, hist, dup, {"source": "mysql", "run": run, "runs": len(runs), "seconds": round(time.time() - t, 1)}


def load():
    """(Re)load the analytics cache: MariaDB -> in-memory DuckDB. Falls back to the parquet."""
    global _con
    s = get_settings()
    con = duckdb.connect(":memory:")
    con.execute("SET threads TO 4")
    info = {}
    try:
        if not s.database_url:
            raise RuntimeError("DATABASE_URL not set")
        df, hist, dup, info = _fetch_mysql()
        for name, frame in (("listings", df), ("history", hist), ("duplicates", dup)):
            if len(frame.columns):
                con.register("src_df", frame)
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM src_df")
                con.unregister("src_df")
    except Exception as e:  # DB unreachable -> keep serving from the bundled snapshot
        log.warning("MySQL load failed (%s); using parquet fallback", e)
        con.execute(f"CREATE TABLE listings AS SELECT * FROM read_parquet('{s.data_path.as_posix()}')")
        dp = s.data_path.parent / "duplicates.parquet"
        if dp.exists():
            con.execute(f"CREATE TABLE duplicates AS SELECT * FROM read_parquet('{dp.as_posix()}')")
        info = {"source": "parquet-fallback", "error": str(e)[:200]}
    with _lock:
        old, _con = _con, con
    if old:
        old.close()
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    if "history" not in tables:
        con.execute("CREATE TABLE history (id BIGINT, run VARCHAR, price_usd DOUBLE, usd_per_m2 DOUBLE)")
    if "duplicates" not in tables:
        con.execute("CREATE TABLE duplicates (type VARCHAR, deal VARCHAR, price_usd DOUBLE, area_m2 DOUBLE, floor DOUBLE, "
                    "subdistrict VARCHAR, street VARCHAR, title VARCHAR, n INT, posters INT, ids VARCHAR)")
    # derived: neighbourhood benchmarks + deal score (z of usd/m2 vs same type/deal/subdistrict/rooms bucket)
    con.execute("""CREATE TABLE bench AS SELECT type, deal, subdistrict,
            CASE WHEN rooms >= 4 THEN 4 ELSE coalesce(rooms, 0) END rb,
            count(*) bn, median(usd_per_m2) b_m2, median(price_usd) b_price
        FROM listings WHERE usd_per_m2 > 0 AND subdistrict IS NOT NULL GROUP BY ALL""")
    con.execute("""CREATE TABLE rent_bench AS SELECT type, subdistrict, median(usd_per_m2) rent_m2, median(price_usd) rent,
        count(*) n FROM listings WHERE deal = 'Rent' AND usd_per_m2 > 0 AND subdistrict IS NOT NULL GROUP BY ALL""")
    con.execute("""CREATE TABLE poster_stats AS SELECT poster, count(*) poster_n FROM listings
        WHERE poster IS NOT NULL GROUP BY 1""")
    n = con.execute("SELECT count(*) FROM listings").fetchone()[0]
    ready.set()
    source_info.clear()
    source_info.update(info, rows=n, loaded_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    log.info("data loaded: %s", source_info)
    return n


ready = threading.Event()


def cur() -> duckdb.DuckDBPyConnection:
    if _con is None:
        if not ready.wait(timeout=90):
            from fastapi import HTTPException
            raise HTTPException(503, "Data is still loading, retry in a few seconds")
    return _con.cursor()  # per-request cursor; thread-safe


def rows(sql: str, params: list | None = None) -> list[dict]:
    c = cur()
    res = c.execute(sql, params or [])
    cols = [d[0] for d in res.description]
    return [dict(zip(cols, r)) for r in res.fetchall()]


def one(sql: str, params: list | None = None) -> dict:
    r = rows(sql, params)
    return r[0] if r else {}


def _csv(v: str | None) -> list[str]:
    return [x for x in (v or "").split(",") if x.strip()]


@dataclass
class Filters:
    type: list[str] = field(default_factory=list)
    deal: list[str] = field(default_factory=list)
    region: str = "tbilisi"
    city: list[str] = field(default_factory=list)
    district: list[str] = field(default_factory=list)
    subdistrict: list[str] = field(default_factory=list)
    rooms: list[str] = field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    m2_min: float | None = None
    m2_max: float | None = None
    area_min: float | None = None
    area_max: float | None = None
    floor_min: int | None = None
    floor_max: int | None = None
    segment: str = ""            # new | resale
    furniture: str = ""          # yes | no
    days: int | None = None      # created within N days
    precision: str = ""          # exact | precise (exact+street)
    seller: str = ""             # broker | owner
    metro_max: float | None = None
    center_max: float | None = None
    q: str = ""

    def where(self, skip: tuple[str, ...] = ()) -> tuple[str, list]:
        """Build WHERE clause. `skip` drops filters a chart breaks down by (e.g. 'deal')."""
        w, p = ["1=1"], []

        def inn(col, vals):
            if vals:
                w.append(f"{col} IN ({','.join('?' * len(vals))})")
                p.extend(vals)

        if "type" not in skip:
            inn("type", self.type)
        if "deal" not in skip:
            inn("deal", self.deal)
        if self.region in ("", "all"):
            pass
        elif self.region == "tbilisi":
            w.append("is_tbilisi")
        elif self.region == "outside":
            w.append("NOT is_tbilisi")
        inn("city", self.city)
        if "district" not in skip:
            inn("district", self.district)
        if "subdistrict" not in skip:
            inn("subdistrict", self.subdistrict)
        if self.rooms:
            parts = []
            for r in self.rooms:
                if r.endswith("+"):
                    parts.append("rooms >= ?")
                    p.append(int(r[:-1]))
                elif r.isdigit():
                    parts.append("rooms = ?")
                    p.append(int(r))
            if parts:
                w.append("(" + " OR ".join(parts) + ")")
        for col, lo, hi in [("price_usd", self.price_min, self.price_max),
                            ("usd_per_m2", self.m2_min, self.m2_max),
                            ("area_m2", self.area_min, self.area_max),
                            ("floor", self.floor_min, self.floor_max)]:
            if lo is not None:
                w.append(f"{col} >= ?")
                p.append(lo)
            if hi is not None:
                w.append(f"{col} <= ?")
                p.append(hi)
        if self.segment == "new":
            w.append("is_project")
        elif self.segment == "resale":
            w.append("NOT is_project")
        if self.furniture == "yes":
            w.append("furniture")
        elif self.furniture == "no":
            w.append("NOT furniture")
        if self.days:
            # relative to the snapshot date, so old snapshots still filter sensibly
            w.append("created >= (SELECT max(created) FROM listings) - to_days(?)")
            p.append(int(self.days))
        if self.precision == "exact":
            w.append("coord_precision = 'exact'")
        elif self.precision == "precise":
            w.append("coord_precision IN ('exact','street')")
        if self.seller == "broker":
            w.append("poster IN (SELECT poster FROM poster_stats WHERE poster_n >= 5)")
        elif self.seller == "owner":
            w.append("poster IN (SELECT poster FROM poster_stats WHERE poster_n < 5)")
        if self.metro_max is not None:
            w.append("metro_km <= ?")
            p.append(self.metro_max)
        if self.center_max is not None:
            w.append("dist_center_km <= ?")
            p.append(self.center_max)
        if self.q:
            w.append("(title ILIKE ? OR street ILIKE ? OR subdistrict ILIKE ? OR CAST(id AS VARCHAR) = ?)")
            like = f"%{self.q}%"
            p.extend([like, like, like, self.q])
        return " AND ".join(w), p


def filters_dep(
    type: str | None = Query(None), deal: str | None = Query(None), region: str = Query("tbilisi"),
    city: str | None = None, district: str | None = None, subdistrict: str | None = None,
    rooms: str | None = None, price_min: float | None = None, price_max: float | None = None,
    m2_min: float | None = None, m2_max: float | None = None, area_min: float | None = None,
    area_max: float | None = None, floor_min: int | None = None, floor_max: int | None = None,
    segment: str = "", furniture: str = "", days: int | None = None, precision: str = "",
    seller: str = "", metro_max: float | None = None, center_max: float | None = None, q: str = "",
) -> Filters:
    return Filters(type=_csv(type), deal=_csv(deal), region=region, city=_csv(city),
                   district=_csv(district), subdistrict=_csv(subdistrict), rooms=_csv(rooms),
                   price_min=price_min, price_max=price_max, m2_min=m2_min, m2_max=m2_max,
                   area_min=area_min, area_max=area_max, floor_min=floor_min, floor_max=floor_max,
                   segment=segment, furniture=furniture, days=days, precision=precision,
                   seller=seller, metro_max=metro_max, center_max=center_max, q=q.strip()[:80])


def filters_from_params(d: dict) -> Filters:
    """Build Filters from a plain dict (saved searches, scheduler)."""
    def num(k, cast=float):
        v = d.get(k)
        try:
            return cast(v) if v not in (None, "") else None
        except ValueError:
            return None
    return Filters(type=_csv(d.get("type")), deal=_csv(d.get("deal")), region=d.get("region", "tbilisi"),
                   city=_csv(d.get("city")), district=_csv(d.get("district")), subdistrict=_csv(d.get("subdistrict")),
                   rooms=_csv(d.get("rooms")), price_min=num("price_min"), price_max=num("price_max"),
                   m2_min=num("m2_min"), m2_max=num("m2_max"), area_min=num("area_min"), area_max=num("area_max"),
                   floor_min=num("floor_min", int), floor_max=num("floor_max", int), segment=d.get("segment", ""),
                   furniture=d.get("furniture", ""), days=num("days", int), precision=d.get("precision", ""),
                   seller=d.get("seller", ""), metro_max=num("metro_max"), center_max=num("center_max"),
                   q=(d.get("q") or "")[:80])
