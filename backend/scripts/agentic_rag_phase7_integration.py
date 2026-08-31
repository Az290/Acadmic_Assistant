"""Discord pilot integration khong can token: real API/DB, fake Discord REST va fake Nova."""

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
from app.connectors.discord.handler import process_discord_outbox  # noqa: E402
from app.db.models import ConnectorOutbox, ExternalMessageEvent  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402

BASE = "http://127.0.0.1:8001"
OUT = Path(__file__).parent / "benchmarks" / "results" / "phase7_discord_integration.json"


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
        row = (await session.execute(
            select(ConnectorOutbox.payload)
            .join(ExternalMessageEvent, ExternalMessageEvent.id == ConnectorOutbox.event_id)
            .where(ExternalMessageEvent.platform == "discord", ExternalMessageEvent.external_event_id == event_id)
        )).scalar_one()
        return json.loads(row)


class FakeRest:
    def __init__(self):
        self.sent = []

    async def send_message(self, channel_id, content, reply_to=None):
        self.sent.append({"channel_id": channel_id, "content": content, "reply_to": reply_to})
        return {"id": str(len(self.sent))}


async def run_handler(payload: dict):
    fake_rest = FakeRest()
    fake_chat = AsyncMock(return_value=SimpleNamespace(
        answer="Tuple khong the thay doi sau khi tao.",
        citations=[{"document_id": 1, "chunk_id": 151, "page_number": 96}],
    ))
    with patch("app.connectors.discord.handler.handle_chat", fake_chat):
        await process_discord_outbox(payload, fake_rest)
    return fake_rest.sent, fake_chat.await_args.kwargs


async def load_and_run_handler(event_id: str):
    payload = await load_payload(event_id)
    sent, call = await run_handler(payload)
    return payload, sent, call


def main() -> int:
    instructor = login("gv.nguyenvana@test.edu.vn", "Instructor@123")
    student = login("sv.sinhvien1@test.edu.vn", "Student@123")
    course = next(c for c in instructor.get("/v1/courses/me").json() if c.get("owner_id"))
    suffix = uuid.uuid4().hex[:10]
    channel_id = f"discord-phase7-{suffix}"
    external_user = "phase7-student1"
    code = student.post("/v1/connectors/link-code", json={"platform": "discord"}).json()["code"]
    linked = student.post("/v1/connectors/discord/link", json={"external_user_id": external_user, "code": code})
    bound = instructor.post("/v1/connectors/discord/channels/bind", json={"channel_id": channel_id, "course_id": course["id"]})
    event_id = f"discord-event-{suffix}"
    envelope = {"external_event_id": event_id, "external_user_id": external_user, "channel_id": channel_id,
                "thread_id": "", "is_group": True, "mentioned_nova": True, "text": "Tuple la gi?",
                "timestamp": "2026-08-31T00:00:00+00:00"}
    raw = json.dumps(envelope, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    secret = get_settings().connector_webhook_secret or get_settings().jwt_secret
    accepted = student.post("/v1/connectors/discord/webhook", content=raw, headers={
        "Content-Type": "application/json", "X-Nova-Timestamp": timestamp,
        "X-Nova-Signature": sign_webhook(secret, timestamp, raw),
    })
    payload, sent, call = asyncio.run(load_and_run_handler(event_id))
    checks = {
        "identity_linked": linked.status_code == 200,
        "channel_bound": bound.status_code == 200,
        "webhook_accepted": accepted.status_code == 200,
        "outbox_keeps_platform": payload.get("platform") == "discord",
        "group_privacy_flag": call.get("is_group") is True,
        "course_scope_forwarded": call.get("course_id") == course["id"],
        "reply_references_message": bool(sent) and sent[0]["reply_to"] == event_id,
        "citation_formatted": bool(sent) and "/documents/1?chunk=151" in sent[0]["content"],
    }
    student.delete("/v1/connectors/discord/identity/me")
    instructor.delete(f"/v1/connectors/discord/channels/{channel_id}/bind")
    report = {"summary": {"cases": len(checks), "passed": sum(checks.values()), "pass_rate": sum(checks.values()) / len(checks)}, "cases": checks}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
