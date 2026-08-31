"""HTTP integration benchmark cho Omnichannel foundation Phase 6."""

import json
import asyncio
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402
from app.connectors.common.security import sign_webhook  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.db.models import ConnectorOutbox, ExternalMessageEvent  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

BASE = "http://127.0.0.1:8001"
RESULT = Path(__file__).parent / "benchmarks" / "results" / "phase6_omnichannel.json"


def login(email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE, timeout=30)
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    for name in ("access_token", "refresh_token"):
        if name in response.cookies:
            client.cookies.set(name, response.cookies[name])
    return client


def signed_post(client: httpx.Client, path: str, payload: dict, *, secret: str, timestamp: int | None = None):
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    sent_at = str(timestamp if timestamp is not None else int(time.time()))
    return client.post(path, content=raw, headers={
        "Content-Type": "application/json",
        "X-Nova-Timestamp": sent_at,
        "X-Nova-Signature": sign_webhook(secret, sent_at, raw),
    })


async def event_counts(external_event_id: str) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        event_count = (await session.execute(select(func.count(ExternalMessageEvent.id)).where(
            ExternalMessageEvent.platform == "mock",
            ExternalMessageEvent.external_event_id == external_event_id,
        ))).scalar_one()
        outbox_count = (await session.execute(select(func.count(ConnectorOutbox.id)).join(
            ExternalMessageEvent, ExternalMessageEvent.id == ConnectorOutbox.event_id
        ).where(
            ExternalMessageEvent.platform == "mock",
            ExternalMessageEvent.external_event_id == external_event_id,
        ))).scalar_one()
        return event_count, outbox_count


def main() -> int:
    instructor = login("gv.nguyenvana@test.edu.vn", "Instructor@123")
    student1 = login("sv.sinhvien1@test.edu.vn", "Student@123")
    student2 = login("sv.sinhvien2@test.edu.vn", "Student@123")
    courses = instructor.get("/v1/courses/me").json()
    owned = next(course for course in courses if course.get("owner_id"))
    course_id = owned["id"]
    suffix = uuid.uuid4().hex[:10]
    channel_id = f"phase6-channel-{suffix}"
    external_user = "phase6-student1"
    cases = []

    def record(name: str, passed: bool, detail: str):
        cases.append({"name": name, "passed": passed, "detail": detail})

    forbidden = student1.post("/v1/connectors/mock/channels/bind", json={"channel_id": channel_id, "course_id": course_id})
    record("student_cannot_bind", forbidden.status_code == 403, str(forbidden.status_code))

    code_response = student1.post("/v1/connectors/link-code", json={"platform": "mock"})
    code = code_response.json()["code"]
    linked = student1.post("/v1/connectors/mock/link", json={"external_user_id": external_user, "code": code})
    record("one_time_link_success", linked.status_code == 200, str(linked.status_code))
    reused = student1.post("/v1/connectors/mock/link", json={"external_user_id": external_user, "code": code})
    record("one_time_link_reuse_blocked", reused.status_code == 400, str(reused.status_code))

    code2 = student2.post("/v1/connectors/link-code", json={"platform": "mock"}).json()["code"]
    takeover = student2.post("/v1/connectors/mock/link", json={"external_user_id": external_user, "code": code2})
    record("identity_takeover_blocked", takeover.status_code == 409, str(takeover.status_code))

    bound = instructor.post("/v1/connectors/mock/channels/bind", json={
        "channel_id": channel_id, "course_id": course_id, "privacy_mode": "MENTION_ONLY",
    })
    record("owner_bind_success", bound.status_code == 200, str(bound.status_code))

    event_id = f"evt-{suffix}"
    payload = {
        "external_event_id": event_id, "external_user_id": external_user,
        "channel_id": channel_id, "thread_id": "", "is_group": True,
        "mentioned_nova": True, "text": "Nova, Python la gi?",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    secret = get_settings().connector_webhook_secret or get_settings().jwt_secret
    bad_sig = student1.post("/v1/connectors/mock/webhook", json=payload, headers={
        "X-Nova-Timestamp": str(int(time.time())), "X-Nova-Signature": "bad",
    })
    record("bad_signature_blocked", bad_sig.status_code == 401, str(bad_sig.status_code))
    replay = signed_post(student1, "/v1/connectors/mock/webhook", payload, secret=secret, timestamp=int(time.time()) - 301)
    record("old_replay_blocked", replay.status_code == 401, str(replay.status_code))
    no_mention = signed_post(student1, "/v1/connectors/mock/webhook", {**payload, "mentioned_nova": False}, secret=secret)
    record("group_without_mention_blocked", no_mention.status_code == 403, str(no_mention.status_code))
    accepted = signed_post(student1, "/v1/connectors/mock/webhook", payload, secret=secret)
    record("signed_event_accepted", accepted.status_code == 200 and not accepted.json()["duplicate"], str(accepted.status_code))
    duplicate = signed_post(student1, "/v1/connectors/mock/webhook", payload, secret=secret)
    record("duplicate_is_idempotent", duplicate.status_code == 200 and duplicate.json()["duplicate"], str(duplicate.status_code))
    event_count, outbox_count = asyncio.run(event_counts(event_id))
    record("exactly_one_event_and_job", event_count == 1 and outbox_count == 1, f"event={event_count},outbox={outbox_count}")

    revoked = student1.delete("/v1/connectors/mock/identity/me")
    after_revoke = signed_post(student1, "/v1/connectors/mock/webhook", {**payload, "external_event_id": f"revoked-{suffix}"}, secret=secret)
    record("revoked_identity_blocked", revoked.status_code == 200 and after_revoke.status_code == 403, f"{revoked.status_code}/{after_revoke.status_code}")
    unbound = instructor.delete(f"/v1/connectors/mock/channels/{channel_id}/bind")
    record("owner_unbind_success", unbound.status_code == 200, str(unbound.status_code))

    report = {"summary": {"cases": len(cases), "passed": sum(c["passed"] for c in cases), "pass_rate": sum(c["passed"] for c in cases) / len(cases)}, "cases": cases}
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    for case in cases:
        print(("PASS" if case["passed"] else "FAIL"), case["name"], case["detail"])
    return 0 if all(case["passed"] for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
