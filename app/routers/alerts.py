"""Saved searches + alerts. Alerts are generated after every data reload (new run):
new-to-feed listings and price drops that match each saved search. Optional Telegram push."""
import json
import logging
import os
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db, store
from ..auth import require_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
log = logging.getLogger("alerts")


class SavedSearchIn(BaseModel):
    name: str = Field(..., max_length=120)
    params: dict
    notify_new: bool = True
    notify_drops: bool = True
    telegram: bool = False


@router.get("/searches", summary="List my saved searches")
def list_searches(p: dict = Depends(require_user)):
    rows = store.q("SELECT * FROM saved_searches WHERE owner=:o ORDER BY id DESC", o=p["user"])
    for r in rows:
        r["params"] = json.loads(r["params"])
        f = db.filters_from_params(r["params"])
        w, pr = f.where()
        r["matches"] = db.one(f"SELECT count(*) n FROM listings WHERE {w}", pr)["n"]
        r["created_at"] = str(r["created_at"])
    return rows


@router.post("/searches", summary="Save a search")
def create_search(body: SavedSearchIn, p: dict = Depends(require_user)):
    params = {k: v for k, v in body.params.items() if v not in (None, "")}
    sid = store.x("""INSERT INTO saved_searches (owner, name, params, notify_new, notify_drops, telegram)
                     VALUES (:o,:n,:p,:a,:b,:t)""", o=p["user"], n=body.name, p=json.dumps(params, ensure_ascii=False),
                  a=int(body.notify_new), b=int(body.notify_drops), t=int(body.telegram))
    return {"id": sid}


@router.delete("/searches/{sid}", summary="Delete a saved search")
def delete_search(sid: int, p: dict = Depends(require_user)):
    n = store.x("DELETE FROM saved_searches WHERE id=:i AND owner=:o", i=sid, o=p["user"])
    if not n:
        raise HTTPException(404, "not found")
    store.x("DELETE FROM alerts WHERE search_id=:i", i=sid)
    return {"deleted": sid}


@router.get("", summary="My alerts (newest first)")
def list_alerts(unread_only: bool = False, limit: int = 100, p: dict = Depends(require_user)):
    rows = store.q(f"""SELECT a.*, s.name search_name FROM alerts a LEFT JOIN saved_searches s ON s.id = a.search_id
        WHERE a.owner=:o {'AND a.is_read=0' if unread_only else ''} ORDER BY a.id DESC LIMIT :l""",
                   o=p["user"], l=min(limit, 500))
    unread = store.q("SELECT count(*) n FROM alerts WHERE owner=:o AND is_read=0", o=p["user"])[0]["n"]
    for r in rows:
        r["created_at"] = str(r["created_at"])
    return {"unread": unread, "rows": rows}


@router.post("/read", summary="Mark all my alerts as read")
def mark_read(p: dict = Depends(require_user)):
    return {"updated": store.x("UPDATE alerts SET is_read=1 WHERE owner=:o AND is_read=0", o=p["user"])}


@router.post("/evaluate", summary="Re-run alert evaluation for the latest run (admin/debug)")
def evaluate_now(p: dict = Depends(require_user)):
    return evaluate()


def _telegram(text: str):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=15).read()
        return True
    except Exception as e:
        log.warning("telegram failed: %s", e)
        return False


def evaluate() -> dict:
    """Create alerts for the newest run vs the previous one. Idempotent (unique key)."""
    runs = [r["run"] for r in db.rows("SELECT DISTINCT run FROM history ORDER BY run DESC LIMIT 2")]
    if len(runs) < 2:
        return {"created": 0, "message": "need 2 runs"}
    cur, prev = runs
    total = 0
    for s in store.q("SELECT * FROM saved_searches"):
        if s["last_run"] == cur:
            continue
        f = db.filters_from_params(json.loads(s["params"]))
        w, p = f.where()
        found = []
        if s["notify_new"]:
            found += [dict(r, kind="new") for r in db.rows(f"""SELECT id, title, subdistrict, price_usd, NULL old_price, url
                FROM listings WHERE {w} AND id NOT IN (SELECT id FROM history WHERE run = ?)
                ORDER BY created DESC LIMIT 50""", p + [prev])]
        if s["notify_drops"]:
            found += [dict(r, kind="drop") for r in db.rows(f"""SELECT l.id, l.title, l.subdistrict, l.price_usd,
                h.price_usd old_price, l.url FROM (SELECT * FROM listings WHERE {w}) l JOIN history h ON h.id = l.id AND h.run = ?
                WHERE l.price_usd < h.price_usd ORDER BY l.price_usd / h.price_usd LIMIT 50""", p + [prev])]
        for r in found:
            detail = (f"{r['subdistrict'] or ''} · ${r['price_usd']:,.0f}"
                      + (f" (was ${r['old_price']:,.0f})" if r["old_price"] else ""))
            total += store.xc("""INSERT IGNORE INTO alerts (search_id, owner, run, kind, listing_id, title, detail,
                price_usd, old_price_usd, url) VALUES (:s,:o,:r,:k,:l,:t,:d,:p,:op,:u)""",
                             s=s["id"], o=s["owner"], r=cur, k=r["kind"], l=r["id"], t=(r["title"] or "")[:255],
                             d=detail[:255], p=r["price_usd"], op=r["old_price"], u=r["url"])
        store.x("UPDATE saved_searches SET last_run=:r WHERE id=:i", r=cur, i=s["id"])
        if s["telegram"] and found:
            n_new = sum(1 for r in found if r["kind"] == "new")
            n_drop = len(found) - n_new
            lines = [f"🏠 {s['name']}: {n_new} new, {n_drop} price drops"] + [
                f"{'↓' if r['kind'] == 'drop' else '•'} {r['title']} — ${r['price_usd']:,.0f} {r['url']}" for r in found[:10]]
            _telegram("\n".join(lines))
    log.info("alerts evaluated for run %s: %s created", cur, total)
    return {"created": total, "run": cur}
