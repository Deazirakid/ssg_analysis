"""Admin: viewer/admin accounts stored in MariaDB + API keys for external apps."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import store
from ..auth import require_admin
from ..config import get_settings

router = APIRouter(prefix="/api/admin", tags=["admin: users & keys"], dependencies=[Depends(require_admin)])


class UserIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(..., min_length=10, max_length=200)
    role: Literal["viewer", "admin"] = "viewer"


class KeyIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    role: Literal["viewer", "admin"] = "viewer"


def _iso(rows):
    for r in rows:
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat(sep=" ", timespec="minutes")
    return rows


@router.get("/users", summary="List accounts")
def list_users():
    rows = _iso(store.q("SELECT id, username, role, active, created_at, last_login FROM app_users ORDER BY id"))
    return [{"id": 0, "username": get_settings().admin_username, "role": "admin", "active": 1,
             "created_at": None, "last_login": None, "builtin": True}] + rows


@router.post("/users", summary="Create an account")
def create_user(u: UserIn):
    if u.username == get_settings().admin_username or store.find_user(u.username):
        raise HTTPException(409, "username exists")
    return {"id": store.x("INSERT INTO app_users (username, pw_hash, role) VALUES (:u,:h,:r)",
                          u=u.username, h=store.hash_pw(u.password), r=u.role)}


@router.post("/users/{uid}/toggle", summary="Activate / deactivate an account")
def toggle_user(uid: int):
    return {"updated": store.x("UPDATE app_users SET active = 1 - active WHERE id=:i", i=uid)}


@router.delete("/users/{uid}", summary="Delete an account")
def delete_user(uid: int):
    return {"deleted": store.x("DELETE FROM app_users WHERE id=:i", i=uid)}


@router.get("/keys", summary="List API keys (hashes only; raw key shown once on creation)")
def list_keys():
    return _iso(store.q("SELECT id, name, prefix, role, active, created_by, created_at, last_used, uses FROM api_keys ORDER BY id DESC"))


@router.post("/keys", summary="Create an API key")
def create_key(k: KeyIn, p: dict = Depends(require_admin)):
    raw = store.new_api_key(k.name, k.role, p["user"])
    return {"key": raw, "note": "Store this now. It cannot be shown again."}


@router.post("/keys/{kid}/revoke", summary="Revoke an API key")
def revoke_key(kid: int):
    return {"updated": store.x("UPDATE api_keys SET active=0 WHERE id=:i", i=kid)}
