import json
from fastapi import APIRouter
from core.registry import list_platforms
from core.config_store import config_store

router = APIRouter(prefix="/platforms", tags=["platforms"])

@router.get("")
def get_platforms():
    return list_platforms()

@router.put("/{name}/capabilities")
def update_platform_capabilities(name: str, body: dict):
    allowed = {"supported_executors", "supported_identity_modes", "supported_oauth_providers"}
    safe = {k: v for k, v in body.items() if k in allowed}
    config_store.set(f"platform_caps.{name}", json.dumps(safe))
    return {"ok": True}

@router.delete("/{name}/capabilities")
def reset_platform_capabilities(name: str):
    config_store.set(f"platform_caps.{name}", "")
    return {"ok": True}
