"""Scrape pipeline control + scheduler.

Scraping needs Light Browser (ss.ge token), so it only runs where PIPELINE_ENABLED=true
(your PC). On the Renode server the page shows status only; data arrives via MariaDB.
"""
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, store
from ..auth import require_admin
from ..config import ROOT

router = APIRouter(prefix="/api/admin/pipeline", tags=["admin: pipeline"], dependencies=[Depends(require_admin)])
LOG = ROOT / "logs" / "pipeline.log"
_state = {"running": False, "started": None, "finished": None, "exit": None, "trigger": None}
_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get("PIPELINE_ENABLED", "").lower() in ("1", "true", "yes")


class Schedule(BaseModel):
    enabled: bool = False
    every_hours: int = Field(24, ge=1, le=24 * 14)
    at_hour: int | None = Field(4, ge=0, le=23, description="preferred local hour; null = any")


def _run(trigger: str):
    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, started=datetime.now().isoformat(timespec="seconds"), exit=None, trigger=trigger)
    LOG.parent.mkdir(exist_ok=True)

    def work():
        with open(LOG, "w", encoding="utf-8") as fh:
            p = subprocess.run([sys.executable, "-u", str(ROOT / "run_all.py")], cwd=ROOT, stdout=fh,
                               stderr=subprocess.STDOUT)
        _state.update(running=False, finished=datetime.now().isoformat(timespec="seconds"), exit=p.returncode)
        store.set_setting("pipeline_last", {"finished": _state["finished"], "exit": p.returncode, "trigger": trigger})
        if p.returncode == 0:
            db.load()
            from .alerts import evaluate
            evaluate()

    threading.Thread(target=work, daemon=True).start()
    return True


@router.get("", summary="Pipeline status, schedule and log tail")
def status():
    tail = ""
    if LOG.exists():
        tail = "".join(LOG.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[-40:])
    return {"enabled": enabled(), "state": _state, "last": store.get_setting("pipeline_last"),
            "schedule": store.get_setting("pipeline_schedule", Schedule().model_dump()), "log": tail}


@router.post("/run", summary="Run scrape → clean → MariaDB now")
def run_now():
    if not enabled():
        raise HTTPException(409, "Pipeline disabled on this host (set PIPELINE_ENABLED=true where Light Browser runs)")
    if not _run("manual"):
        raise HTTPException(409, "already running")
    return {"started": True}


@router.put("/schedule", summary="Set the automatic schedule")
def set_schedule(s: Schedule):
    store.set_setting("pipeline_schedule", s.model_dump())
    return s


def scheduler_loop():
    """Checks every minute; runs when enabled and the interval has elapsed (and preferred hour matches)."""
    while True:
        time.sleep(60)
        try:
            if not enabled():
                continue
            s = Schedule(**store.get_setting("pipeline_schedule", {}))
            if not s.enabled or _state["running"]:
                continue
            last = (store.get_setting("pipeline_last") or {}).get("finished")
            due = not last or (datetime.now() - datetime.fromisoformat(last)).total_seconds() >= s.every_hours * 3600 - 300
            if due and (s.at_hour is None or s.every_hours < 24 or datetime.now().hour == s.at_hour):
                _run("schedule")
        except Exception:
            pass
