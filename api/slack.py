import os
import hmac
import hashlib
import time
from fastapi import Request, HTTPException

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")


async def verify_slack_signature(request: Request):
    """Slack HMAC 서명 검증 — 위조 요청 차단."""
    if not SLACK_SIGNING_SECRET:
        raise HTTPException(status_code=500, detail="SLACK_SIGNING_SECRET 미설정")

    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not timestamp or not signature:
        raise HTTPException(status_code=400, detail="Missing Slack headers")

    if abs(time.time() - int(timestamp)) > 300:
        raise HTTPException(status_code=400, detail="Request too old")

    body = await request.body()
    sig_base = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_base.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")
