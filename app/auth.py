"""Authentication & authorization.

- Superadmin: ADMIN_USERNAME / ADMIN_PASSWORD from .env (always works, even if DB is down)
- DB users (app_users): role 'admin' or 'viewer', PBKDF2-hashed passwords
- API keys (api_keys): header `X-API-Key: ssk_...` or `?api_key=` (for Google Sheets IMPORTDATA)
- Session: signed cookie (Starlette SessionMiddleware); throttled login; audit log (file + DB)
"""
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from logging.handlers import RotatingFileHandler

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery

from . import store
from .config import get_settings

_s = get_settings()
_s.log_dir.mkdir(parents=True, exist_ok=True)
audit = logging.getLogger("auth")
audit.setLevel(logging.INFO)
if not audit.handlers:
    h = RotatingFileHandler(_s.log_dir / "auth.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    audit.addHandler(h)
    audit.addHandler(logging.StreamHandler())

_attempts: dict[str, deque] = defaultdict(deque)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="API key (ssk_...) created in Admin → API keys")
api_key_query = APIKeyQuery(name="api_key", auto_error=False, description="Same key as query param, e.g. for Google Sheets IMPORTDATA")


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def record(event: str, request: Request, username: str | None):
    ip, ua = client_ip(request), (request.headers.get("user-agent") or "")[:255]
    (audit.info if event in ("login_ok", "logout") else audit.warning)("%s ip=%s user=%r", event, ip, username)

    def _w():
        try:
            store.x("INSERT INTO auth_log (event, username, ip, user_agent) VALUES (:e,:u,:i,:a)",
                    e=event, u=(username or "")[:64], i=ip[:64], a=ua)
        except Exception as e:
            audit.error("auth_log db write failed: %s", e)

    threading.Thread(target=_w, daemon=True).start()


def throttled(ip: str) -> bool:
    q, now = _attempts[ip], time.time()
    while q and now - q[0] > _s.login_window_sec:
        q.popleft()
    return len(q) >= _s.login_max_attempts


def _verify(username: str, password: str) -> str | None:
    """Returns role or None."""
    if secrets.compare_digest(username.encode(), _s.admin_username.encode()) and \
            secrets.compare_digest(password.encode(), _s.admin_password.encode()):
        return "admin"
    try:
        u = store.find_user(username)
    except Exception:
        u = None
    if u and store.verify_pw(password, u["pw_hash"]):
        threading.Thread(target=store.touch_user, args=(username,), daemon=True).start()
        return u["role"]
    return None


def check_credentials(request: Request, username: str, password: str) -> bool:
    ip = client_ip(request)
    if throttled(ip):
        record("login_throttled", request, username)
        return False
    role = _verify(username, password)
    if role:
        _attempts.pop(ip, None)
        request.session.clear()
        request.session.update(user=username, role=role, exp=int(time.time()) + _s.session_hours * 3600)
        record("login_ok", request, username)
        return True
    _attempts[ip].append(time.time())
    record("login_failed", request, username)
    return False


def session_principal(request: Request) -> dict | None:
    user, exp = request.session.get("user"), request.session.get("exp", 0)
    if user and exp > time.time():
        role = request.session.get("role") or ("admin" if user == _s.admin_username else "viewer")
        return {"user": user, "role": role, "via": "session"}
    if user:
        request.session.clear()
    return None


def current_user(request: Request) -> str | None:
    p = session_principal(request)
    return p["user"] if p else None


def principal(request: Request, hk: str | None = Security(api_key_header),
              qk: str | None = Security(api_key_query)) -> dict:
    p = session_principal(request)
    if p:
        return p
    key = hk or qk
    if key:
        k = store.check_api_key(key)
        if k:
            return {"user": f"apikey:{k['name']}", "role": k["role"], "via": "api_key"}
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


def require_user(p: dict = Depends(principal)) -> dict:
    return p


def require_admin(p: dict = Depends(principal)) -> dict:
    if p["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return p


def logout(request: Request):
    record("logout", request, request.session.get("user"))
    request.session.clear()
