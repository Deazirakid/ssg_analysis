import threading

from fastapi import APIRouter, Depends
from sqlalchemy import text

from .. import db
from ..auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
_reloading = threading.Event()


@router.get("/status")
def status():
    runs, logins = [], []
    eng = db.engine()
    if eng is not None:
        try:
            with eng.connect() as c:
                runs = [dict(r._mapping) for r in c.execute(text(
                    "SELECT run, loaded_at, listings FROM scrape_runs ORDER BY run DESC LIMIT 10"))]
                logins = [dict(r._mapping) for r in c.execute(text(
                    "SELECT ts, event, username, ip FROM auth_log ORDER BY id DESC LIMIT 25"))]
        except Exception as e:
            runs = [{"error": str(e)[:200]}]
    for r in runs + logins:
        for k, v in r.items():
            r[k] = str(v) if v is not None and not isinstance(v, (int, float, str)) else v
    return {"source": db.source_info, "reloading": _reloading.is_set(), "runs": runs, "logins": logins}


@router.post("/reload")
def reload():
    """Re-pull listings from MariaDB into the in-memory analytics cache."""
    if _reloading.is_set():
        return {"started": False, "message": "already reloading"}

    def _run():
        _reloading.set()
        try:
            db.load()
            from .alerts import evaluate
            evaluate()
        finally:
            _reloading.clear()

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True}
