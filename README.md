# ss.ge Market Panel

A data pipeline plus an admin dashboard for the Georgian real-estate market, using home.ss.ge listings.

- **Pipeline** (`src/`): scrape ss.ge (48 threads), clean, build the Excel and HTML heatmap, then load MariaDB.
- **Web app** (`app/`): FastAPI admin dashboard with Mapbox maps, analytics, filters, a listings table and CSV export.
- **Database**: MariaDB on Renode (`DATABASE_URL`), shared by local and production.

## Run locally

```
pip install -r requirements.txt
python app.py                      # http://localhost:8000  (SERVER_PORT / PORT respected)
```

Sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env` (copy `.env.example` to start).

On startup the app pulls the `listings` table from MariaDB into an in-memory DuckDB cache. That takes about 15 s for 183k rows, and it is what makes medians, percentiles and grids fast. If the database is unreachable, the app serves the bundled `data/app/listings.parquet` instead.

## Features (v2)

| Page | What |
|---|---|
| Overview / Map / Analytics | KPIs, Mapbox price grid + heatmap + clusters + 3D, metro stations, walk-time isochrones (Mapbox Isochrone API) with in-polygon stats |
| Deals & drops | Below-market listings (vs neighbourhood + room-count median, 15–60% off) and price changes between the two latest scrape runs |
| Trends & DOM | Weekly median USD/m², neighbourhood trend lines, days on market, delisting rate between runs |
| Compare areas | Up to 4 neighbourhoods side by side (price, IQR, rent, yield, metro/centre distance, rooms) |
| Buildings | Units sharing one exact pin (≈ building), new-build share, premium vs resale nearby |
| Sellers | Broker vs owner split (poster with 5+ active listings = broker), pricing gap, top posters (salted hash IDs) |
| Metro & centre | Price curves by distance to nearest metro / Freedom Square, per-station medians |
| Short-term rentals | Daily-rent supply by month and place, nightly prices |
| Investment calc | Mortgage, cash flow, cash-on-cash, break-even, 10-year return; pre-filled from a listing + rent comps |
| Listings | Table + CSV / Excel export + live Google Sheets `IMPORTDATA` feed (API key) |
| Saved searches | Save any filter set → alerts for new listings and price drops after each refresh, bell + optional Telegram |
| Fraud & quality (admin) | Suspiciously low prices, duplicate clusters, template titles, heavy posters |
| Users & API keys (admin) | DB viewer/admin accounts (PBKDF2), hashed API keys for external apps |
| Data & pipeline (admin) | Data source, reload, run scraper, schedule, logs, sign-in log |
| `/docs` (admin) | Swagger UI. Use the session cookie, or **Authorize** with `X-API-Key` |

Roles: **admin** (the `.env` superuser plus DB admins) sees everything. **viewer** sees the dashboards only. API keys carry a role too.

Extra env: `PIPELINE_ENABLED=true` only on the PC with Light Browser. `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` are optional.

## Refresh data

```
pip install -r requirements-pipeline.txt
python run_all.py                  # scrape -> clean -> excel/heatmap -> parquet -> MariaDB
```

Scraping reads the ss.ge token from Light Browser, so it must run on this PC. Afterwards, open **Data & admin** and click **Reload from database** in the running app.

## App layout

| Path | Purpose |
|---|---|
| `app.py` | Entry point (Renode Python egg runs `python app.py`, binds `0.0.0.0:$SERVER_PORT`) |
| `app/config.py` | Settings from `.env` |
| `app/auth.py` | Single admin login, signed session cookie, 5 tries / 5 min throttle, audit to `logs/auth.log` + `auth_log` table |
| `app/db.py` | MariaDB → DuckDB cache, shared `Filters` → SQL builder |
| `app/routers/overview.py` | KPIs, neighbourhoods, daily flow, histogram, rooms, mix |
| `app/routers/analytics.py` | Rental yield, district spread, scatter, floors, segments, streets |
| `app/routers/geo.py` | Map points, price grid, listing popup |
| `app/routers/listings.py` | Paged/sorted table + CSV export |
| `app/routers/admin.py` | Data source status, scrape runs, sign-in log, reload |
| `app/static/js/filters.js` | Global filter bar (URL + localStorage, carried across pages) |
| `app/static/js/map.js` | Mapbox GL: price grid / 3D, heatmap, points, clusters |

## MariaDB tables

`listings` (current snapshot, swapped atomically) · `price_history` (price per listing per run, which enables price-drop tracking) · `scrape_runs` · `auth_log`.

## Deploy on Renode (Python egg)

1. Create a server from the Python 3.12 egg. The entry file is `app.py` (the default).
2. Upload the project. Don't upload `.env`; set the variables from `.env.example` in the panel's startup variables or environment.
3. Set `COOKIE_SECURE=true` once the site is served over HTTPS.
4. Restart. The health check is at `GET /healthz`.

Not committed (see `.gitignore`): `.env`, `logs/`, `data/raw`, `data/clean`, `output/`. `data/app/listings.parquet` (6.7 MB) is kept as the offline fallback.

## Cleaning rules

See `src/clean.py`:
- Unpinned listings get street- or subdistrict-median coordinates (`coord_precision`).
- Price outliers are flagged with a robust z-score.
- Reposts are de-duplicated.
- Phones, names, descriptions and user IDs are never stored in the clean or app data.
