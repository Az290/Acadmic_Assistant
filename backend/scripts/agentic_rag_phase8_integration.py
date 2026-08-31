"""Zalo OA integration: real API/DB, fake Nova and fake Zalo REST."""
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402
from app.connectors.common.security import sign_webhook  # noqa: E402
from app.connectors.zalo.handler import process_zalo_outbox  # noqa: E402
from app.db.models import ConnectorOutbox, ExternalMessageEvent  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402

BASE = "http://127.0.0.1:8001"
OUT = Path(__file__).parent / "benchmarks" / "results" / "phase8_zalo_integration.json"


def login(email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE, timeout=30)
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    for name in ("access_token", "refresh_token"):
        if name in response.cookies:
            client.cookies.set(name, response.cookies[name])
    return client


async def load_payload(event_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        raw = (await session.execute(
            select(ConnectorOutbox.payload).join(
                ExternalMessageEvent, ExternalMessageEvent.id == ConnectorOutbox.event_id
            ).where(ExternalMessageEvent.platform == "zalo",
                    ExternalMessageEvent.external_event_id == event_id)
        )).scalar_one()
        return json.loads(raw)


class FakeRest:
    def __init__(self):
        self.sent = []

    async def send_text(self, user_id, text):
        self.sent.append({"user_id": user_id, "text": text})
        return {"error": 0}


async def run_handler(payload: dict):
    rest = FakeRest()
    chat = AsyncMock(return_value=SimpleNamespace(
        answer="Machine learning la mot nhanh cua AI.", citations=[]
    ))
    with patch("app.connectors.zalo.handler.handle_chat", chat):
        await process_zalo_outbox(payload, rest)
    return rest.sent, chat.await_args.kwargs


async def load_and_run_handler(event_id: str):
    payload = await load_payload(event_id)
    sent, call = await run_handler(payload)
    return payload, sent, call


def main() -> int:
    student = login("sv.sinhvien2@test.edu.vn", "Student@123")
    # Make reruns deterministic after an interrupted benchmark.
    student.delete("/v1/connectors/zalo/identity/me")
    external_user = "zalo-phase8-student2"
    code = student.post("/v1/connectors/link-code", json={"platform": "zalo"}).json()["code"]
    linked = student.post("/v1/connectors/zalo/link", json={"external_user_id": external_user, "code": code})
    event_id = f"zalo-event-{uuid.uuid4().hex[:10]}"
    envelope = {"external_event_id": event_id, "external_user_id": external_user,
                "channel_id": external_user, "thread_id": "oa", "is_group": False,
                "mentioned_nova": True, "text": "Machine learning la gi?",
                "timestamp": "2026-08-31T00:00:00+00:00"}
    raw = json.dumps(envelope, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    secret = get_settings().connector_webhook_secret or get_settings().jwt_secret
    headers = {"Content-Type": "application/json", "X-Nova-Timestamp": timestamp,
               "X-Nova-Signature": sign_webhook(secret, timestamp, raw)}
    accepted = student.post("/v1/connectors/zalo/webhook", content=raw, headers=headers)
    duplicate = student.post("/v1/connectors/zalo/webhook", content=raw, headers=headers)
    payload, sent, call = asyncio.run(load_and_run_handler(event_id))
    checks = {
        "identity_linked": linked.status_code == 200,
        "webhook_accepted": accepted.status_code == 200 and not accepted.json()["duplicate"],
        "duplicate_idempotent": duplicate.status_code == 200 and duplicate.json()["duplicate"],
        "outbox_platform": payload.get("platform") == "zalo",
        "private_scope": call.get("is_group") is False and call.get("course_id") is None,
        "exact_recipient": len(sent) == 1 and sent[0]["user_id"] == external_user,
        "answer_formatted": bool(sent) and "Machine learning" in sent[0]["text"],
    }
    student.delete("/v1/connectors/zalo/identity/me")
    report = {"summary": {"cases": len(checks), "passed": sum(checks.values()),
                           "pass_rate": sum(checks.values()) / len(checks)}, "cases": checks}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
