from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import auth
from ..config import get_settings

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")

# key: (path, title, icon (lucide), group, admin_only, description)
PAGES = {
    "overview":  ("/", "Overview", "layout-dashboard", "Dashboard", False, "Market pulse for the current filters"),
    "map":       ("/map", "Map", "map", "Dashboard", False, "Price grid, density, clusters and walk-time isochrones"),
    "analytics": ("/analytics", "Analytics", "bar-chart-3", "Dashboard", False, "Yield, spread, floors, segments and streets"),
    "deals":     ("/deals", "Deals & drops", "badge-percent", "Intelligence", False, "Below-market listings and price changes between runs"),
    "trends":    ("/trends", "Trends & DOM", "trending-up", "Intelligence", False, "Weekly price trend, days on market, delisting rate"),
    "compare":   ("/compare", "Compare areas", "columns-3", "Intelligence", False, "Up to four neighbourhoods side by side"),
    "projects":  ("/projects", "Buildings", "building-2", "Intelligence", False, "Multi-unit buildings and new-build projects vs resale nearby"),
    "sellers":   ("/sellers", "Sellers", "users", "Intelligence", False, "Broker vs owner split and top posters"),
    "location":  ("/location", "Metro & centre", "train-front", "Intelligence", False, "Price curves by distance to metro and city centre"),
    "rentals":   ("/rentals", "Short-term rentals", "sun", "Intelligence", False, "Daily-rent supply and nightly prices by place and month"),
    "invest":    ("/invest", "Investment calc", "calculator", "Intelligence", False, "Mortgage, cash flow, yield and break-even for a listing"),
    "listings":  ("/listings", "Listings", "table-2", "Data", False, "Searchable table with CSV / Excel / Sheets export"),
    "alerts":    ("/alerts", "Saved searches", "bell-ring", "Data", False, "Saved filters, alerts on new listings and price drops"),
    "quality":   ("/quality", "Fraud & quality", "shield-alert", "Admin", True, "Duplicates, suspicious prices, heavy posters"),
    "users":     ("/users", "Users & API keys", "key-round", "Admin", True, "Viewer accounts and keys for external apps"),
    "admin":     ("/admin", "Data & pipeline", "database", "Admin", True, "Data source, scrape runs, schedule, sign-in log"),
}


def _page(request: Request, name: str):
    p = auth.session_principal(request)
    path, title, icon, group, admin_only, desc = PAGES[name]
    if not p:
        return RedirectResponse(f"/login?next={path}", status_code=303)
    if admin_only and p["role"] != "admin":
        return RedirectResponse("/", status_code=303)
    s = get_settings()
    nav = {}
    for k, v in PAGES.items():
        if v[4] and p["role"] != "admin":
            continue
        nav.setdefault(v[3], []).append((k, v))
    return templates.TemplateResponse(request, f"{name}.html", {
        "user": p["user"], "role": p["role"], "page": name, "nav": nav, "title": title, "desc": desc,
        "mapbox_token": s.mapbox_token, "mapbox_style": s.mapbox_style,
    })


def _make(name):
    def view(request: Request):
        return _page(request, name)
    return view


for _k, _v in PAGES.items():
    router.add_api_route(_v[0], _make(_k), methods=["GET"], response_class=HTMLResponse, name=f"page_{_k}")


def _safe_next(n: str | None) -> str:
    return n if n and n.startswith("/") and not n.startswith("//") else "/"


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/"):
    if auth.current_user(request):
        return RedirectResponse(_safe_next(next), status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next": _safe_next(next), "error": None})


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/")):
    if auth.check_credentials(request, username.strip(), password):
        return RedirectResponse(_safe_next(next), status_code=303)
    msg = ("Too many attempts. Wait a few minutes." if auth.throttled(auth.client_ip(request))
           else "Wrong username or password.")
    return templates.TemplateResponse(request, "login.html", {"next": _safe_next(next), "error": msg},
                                      status_code=401)


@router.post("/logout")
def logout(request: Request):
    auth.logout(request)
    return RedirectResponse("/login", status_code=303)
