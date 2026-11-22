"""App-owned MariaDB tables: users, API keys, saved searches, alerts, settings."""
import hashlib
import hmac
import json
import logging
import secrets

from sqlalchemy import text

from . import db

log = logging.getLogger("store")

DDL = [
    """CREATE TABLE IF NOT EXISTS app_users (
         id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(64) UNIQUE NOT NULL,
         pw_hash VARCHAR(200) NOT NULL, role VARCHAR(16) NOT NULL DEFAULT 'viewer',
         active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
         last_login DATETIME NULL) DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS api_keys (
         id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) NOT NULL, prefix CHAR(8) NOT NULL,
         key_hash CHAR(64) UNIQUE NOT NULL, role VARCHAR(16) NOT NULL DEFAULT 'viewer',
         active TINYINT(1) NOT NULL DEFAULT 1, created_by VARCHAR(64), created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
         last_used DATETIME NULL, uses BIGINT NOT NULL DEFAULT 0) DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS saved_searches (
         id INT AUTO_INCREMENT PRIMARY KEY, owner VARCHAR(64) NOT NULL, name VARCHAR(120) NOT NULL,
         params TEXT NOT NULL, notify_new TINYINT(1) DEFAULT 1, notify_drops TINYINT(1) DEFAULT 1,
         telegram TINYINT(1) DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
         last_run VARCHAR(16) NULL, KEY ix_owner (owner)) DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS alerts (
         id BIGINT AUTO_INCREMENT PRIMARY KEY, search_id INT, owner VARCHAR(64), run VARCHAR(16),
         kind VARCHAR(16), listing_id BIGINT, title VARCHAR(255), detail VARCHAR(255),
         price_usd DOUBLE, old_price_usd DOUBLE, url VARCHAR(400), is_read TINYINT(1) DEFAULT 0,
         created_at DATETIME DEFAULT CURRENT_TIMESTAMP, KEY ix_owner_read (owner, is_read),
         UNIQUE KEY ux_alert (search_id, run, kind, listing_id)) DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS app_settings (
         k VARCHAR(64) PRIMARY KEY, v TEXT) DEFAULT CHARSET=utf8mb4""",
]


def init():
    eng = db.engine()
    if eng is None:
        return
    with eng.begin() as c:
        for d in DDL:
            c.execute(text(d))


def q(sql, **p):
    with db.engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), p)]


def x(sql, **p):
    """Execute; returns new row id for INSERTs with auto-increment, else affected row count."""
    with db.engine().begin() as c:
        r = c.execute(text(sql), p)
        return r.lastrowid if r.lastrowid else r.rowcount


def xc(sql, **p):
    """Execute; always returns affected row count."""
    with db.engine().begin() as c:
        return c.execute(text(sql), p).rowcount


# ---------- passwords ----------
def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 240_000).hex()
    return f"pbkdf2$240000${salt}${h}"


def verify_pw(pw: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it)).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


# ---------- users ----------
def find_user(username: str):
    r = q("SELECT * FROM app_users WHERE username=:u AND active=1", u=username)
    return r[0] if r else None


def touch_user(username: str):
    x("UPDATE app_users SET last_login=NOW() WHERE username=:u", u=username)


# ---------- api keys ----------
def new_api_key(name: str, role: str, by: str) -> str:
    raw = "ssk_" + secrets.token_urlsafe(32)
    x("INSERT INTO api_keys (name, prefix, key_hash, role, created_by) VALUES (:n,:p,:h,:r,:b)",
      n=name[:80], p=raw[4:12], h=hashlib.sha256(raw.encode()).hexdigest(), r=role, b=by)
    return raw


def check_api_key(raw: str):
    if not raw or not raw.startswith("ssk_"):
        return None
    h = hashlib.sha256(raw.encode()).hexdigest()
    try:
        r = q("SELECT id, name, role FROM api_keys WHERE key_hash=:h AND active=1", h=h)
    except Exception as e:
        log.warning("api key lookup failed: %s", e)
        return None
    if not r:
        return None
    x("UPDATE api_keys SET last_used=NOW(), uses=uses+1 WHERE id=:i", i=r[0]["id"])
    return r[0]


# ---------- settings ----------
def get_setting(k, default=None):
    try:
        r = q("SELECT v FROM app_settings WHERE k=:k", k=k)
        return json.loads(r[0]["v"]) if r else default
    except Exception:
        return default


def set_setting(k, v):
    x("REPLACE INTO app_settings (k, v) VALUES (:k, :v)", k=k, v=json.dumps(v))
