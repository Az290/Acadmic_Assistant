"""Public Zalo OA webhook adapter -> signed internal connector webhook.

Deploy this process behind HTTPS. ZALO_CALLBACK_SECRET is mandatory and must be
checked by the reverse proxy/callback URL header; provider-specific verification
can be added when the approved OA contract exposes it.
"""
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.connectors.common.security import sign_webhook  # noqa: E402
from app.connectors.zalo.adapter import normalize_oa_event, parse_link_command  # noqa: E402
from app.connectors.zalo.rest import ZaloOARestClient  # noqa: E402

app = FastAPI(title="Nova Zalo OA Adapter")


@app.post("/zalo/webhook")
async def receive_zalo_event(request: Request, x_nova_callback_secret: str = Header(default="")):
    settings = get_settings()
    if not settings.zalo_connector_enabled:
        raise HTTPException(status_code=503, detail="Zalo connector dang tat")
    if not settings.zalo_callback_secret or x_nova_callback_secret != settings.zalo_callback_secret:
        raise HTTPException(status_code=401, detail="Callback secret khong hop le")
    payload = await request.json()
    envelope = normalize_oa_event(payload, gmf_enabled=settings.zalo_gmf_enabled)
    if envelope is None:
        return {"accepted": False, "ignored": True}
    client = ZaloOARestClient(settings.zalo_oa_access_token or "")
    code = parse_link_command(envelope.text)
    async with httpx.AsyncClient(timeout=10) as http:
        if code:
            response = await http.post(
                f"{settings.zalo_internal_api_base.rstrip('/')}/v1/connectors/zalo/link",
                json={"external_user_id": envelope.external_user_id, "code": code},
            )
            if response.is_success:
                await client.send_text(envelope.external_user_id, "Da lien ket Nova voi tai khoan cua ban.")
            else:
                await client.send_text(envelope.external_user_id, "Ma lien ket khong hop le hoac da het han.")
            return {"accepted": response.is_success, "linked": response.is_success}
        body = envelope.model_dump_json().encode("utf-8")
        timestamp = str(int(time.time()))
        signature = sign_webhook(settings.connector_webhook_secret or settings.jwt_secret, timestamp, body)
        response = await http.post(
            f"{settings.zalo_internal_api_base.rstrip('/')}/v1/connectors/zalo/webhook",
            content=body,
            headers={"Content-Type": "application/json", "X-Nova-Timestamp": timestamp,
                     "X-Nova-Signature": signature},
        )
        response.raise_for_status()
    return {"accepted": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8011)
