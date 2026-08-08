"""
The Void -- Moltbook Webhook Router
(c) ZQM Computing LLC -- Proprietary

Mounts a separate Moltbook webhook endpoint at:
  /api/webhooks/moltbook
"""

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.routers.webhooks import _ingest_webhook_event

logger = logging.getLogger("zqm_ai.moltbook")

router = APIRouter(prefix="/api/webhooks", tags=["moltbook"])


def _verify_signature(body: bytes, signature: Optional[str], secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/moltbook", summary="Moltbook webhook receiver")
async def moltbook_webhook(
    request: Request,
    x_moltbook_signature: Optional[str] = Header(None, alias="X-Moltbook-Signature"),
    x_moltbook_event: Optional[str] = Header(None, alias="X-Moltbook-Event"),
):
    """
    Receive Moltbook platform events.

    Configure in Moltbook integration settings:
      URL: http://<zqm_ai-host>:8808/api/webhooks/moltbook
      Auth: HMAC-SHA256 via X-Moltbook-Signature
      Secret: <MOLTBOOK_WEBHOOK_SECRET>
    """
    body = await request.body()
    secret = os.getenv("MOLTBOOK_WEBHOOK_SECRET", "")
    if secret:
        if not x_moltbook_signature:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Moltbook signature")
        if not _verify_signature(body, x_moltbook_signature, secret):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Moltbook signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON body")

    event = x_moltbook_event or payload.get("event") or payload.get("type") or "unknown"
    data = {
        "summary": f"Moltbook event: {event}",
        "event": event,
        "payload": payload,
        "resource": payload.get("resource"),
    }
    result = await _ingest_webhook_event("moltbook", event, data)
    return {"status": "received", "event": event, "result": result}
