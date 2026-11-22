import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, db, store
from .config import get_settings
from .routers import (admin, alerts, analytics, export, geo, listings, market, meta, overview, pages,
                      pipeline, users)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")

DESCRIPTION = """
Georgian real-estate market data from **home.ss.ge** (all property types × deal types), cleaned and
enriched (neighbourhood benchmarks, metro distance, price history).

### Authentication
* **Browser:** sign in at `/login`. Swagger then uses your session cookie automatically.
* **External apps:** create a key in *Admin → Users & API keys* and send it as `X-API-Key: ssk_...`
  (or `?api_key=ssk_...` for tools like Google Sheets `IMPORTDATA`). Click **Authorize** above to try it.

### Filters
Most endpoints accept the same filter query params: `type`, `deal`, `region` (`tbilisi` default, `all`, `outside`),
`city`, `district`, `subdistrict`, `rooms` (e.g. `1,2,5+`), `price_min/max`, `m2_min/max`, `area_min/max`,
`floor_min/max`, `segment` (`new`|`resale`), `furniture` (`yes`|`no`), `days`, `precision` (`exact`|`precise`),
`seller` (`broker`|`owner`), `metro_max`, `center_max` (km), `q`. Multi-values are comma-separated.
"""


def _startup_load():
    try:
        store.init()
    except Exception as e:
        log.warning("store init failed: %s", e)
    db.load()
    try:
        alerts.evaluate()
    except Exception as e:
        log.warning("alert evaluation failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_startup_load, daemon=True).start()
    threading.Thread(target=pipeline.scheduler_loop, daemon=True).start()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="ss.ge Market API", version="2.0", description=DESCRIPTION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None,
                  openapi_tags=[{"name": "overview"}, {"name": "market", "description": "Deals, drops, trends, compare, projects, sellers, fraud"},
                                {"name": "map"}, {"name": "analytics"}, {"name": "listings"}, {"name": "export"},
                                {"name": "alerts"}, {"name": "meta"}])
    app.add_middleware(SessionMiddleware, secret_key=s.secret_key, session_cookie="ssge_session",
                       max_age=s.session_hours * 3600, same_site="lax", https_only=s.cookie_secure)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return JSONResponse({"ok": True, "data": db.source_info or "loading"})

    # ---- Swagger: admins only ----
    @app.get("/openapi.json", include_in_schema=False)
    def openapi_json(_: dict = Depends(auth.require_admin)):
        return app.openapi()

    @app.get("/docs", include_in_schema=False)
    def docs(request: Request):
        p = auth.session_principal(request)
        if not p:
            return RedirectResponse("/login?next=/docs", status_code=303)
        if p["role"] != "admin":
            return RedirectResponse("/", status_code=303)
        return get_swagger_ui_html(openapi_url="/openapi.json", title="ss.ge Market API",
                                   swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True,
                                                          "docExpansion": "none", "filter": True})

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    for r in (pages, meta, overview, market, analytics, geo, listings, export, alerts, admin, users, pipeline):
        app.include_router(r.router)
    return app


app = create_app()
