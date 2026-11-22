"""Gets a fresh ss.ge bearer token from Light Browser (ss-session-token cookie).

The token is an anonymous next-auth client token (~1h lifetime). On expiry we
reload an ss.ge tab so the site re-issues the cookie, then read it again.
"""
import json
import os
import subprocess
import threading
import time
import base64

LBAI = os.environ.get(
    "LBAI", r"C:\Users\davit\AppData\Local\LightBrowser\Profile\ai\lbai.mjs"
)
SS_URL = "https://home.ss.ge/ka/udzravi-qoneba/l/bina/iyideba"
JS_COOKIE = (
    "(()=>{const c=document.cookie.split('; ').find(x=>x.startsWith('ss-session-token='));"
    "return c?decodeURIComponent(c.split('=').slice(1).join('=')):''})()"
)


def _lbai(*args, timeout=60):
    out = subprocess.run(
        ["node", LBAI, *args], capture_output=True, text=True,
        encoding="utf-8", timeout=timeout,
    )
    if out.returncode != 0:
        raise RuntimeError(f"lbai {args[0]} failed: {out.stderr.strip() or out.stdout.strip()}")
    return out.stdout.strip()


def _find_ss_tab():
    for line in _lbai("tabs").splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit() and "https://home.ss.ge" in line and "[asleep]" not in line:
            return parts[0]
    return None


def jwt_exp(tok):
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))["exp"]
    except Exception:
        return 0


class TokenProvider:
    def __init__(self):
        self._lock = threading.Lock()
        self._token = os.environ.get("SS_TOKEN", "")
        self._tab = None

    def _read(self, reload=False):
        tab = self._tab or _find_ss_tab()
        if tab is None:
            _lbai("open", SS_URL, "--bg")
            time.sleep(6)
            tab = _find_ss_tab()
            if tab is None:
                raise RuntimeError("Could not open an ss.ge tab in Light Browser")
        self._tab = tab
        if reload:
            _lbai("reload", "--tab", tab)
            try:
                _lbai("wait", "load", "--tab", tab, "--timeout", "20000", timeout=40)
            except RuntimeError:
                pass
            time.sleep(2)
        return _lbai("eval", JS_COOKIE, "--tab", tab)

    def get(self):
        with self._lock:
            if not self._token or jwt_exp(self._token) - time.time() < 120:
                self._refresh_locked()
            return self._token

    def invalidate(self, bad_token):
        """Called on 401. Only one thread refreshes; others reuse the new token."""
        with self._lock:
            if self._token == bad_token:
                self._refresh_locked(force_reload=True)
            return self._token

    def _refresh_locked(self, force_reload=False):
        tok = "" if force_reload else self._read()
        if not tok or jwt_exp(tok) - time.time() < 120:
            tok = self._read(reload=True)
        if not tok:
            raise RuntimeError("ss-session-token cookie not found in Light Browser")
        self._token = tok
        left = int((jwt_exp(tok) - time.time()) / 60)
        print(f"[token] refreshed from Light Browser, valid ~{left} min", flush=True)
