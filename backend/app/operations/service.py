import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.connectors.common.outbox import recover_stale_outbox
from app.db.models import ConnectorOutbox, ExternalIdentityLinkCode, ExternalMessageEvent, Message


@dataclass(frozen=True)
class OperationsSnapshot:
    pending_jobs: int
    processing_jobs: int
    dead_jobs: int
    oldest_pending_seconds: int
    p95_chat_latency_ms: int | None
    rollout_percent: int
    rollback_recommended: bool
    rollback_reasons: list[str]


def percentile95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(0.95 * len(ordered) + 0.999) - 1))]


async def get_operations_snapshot(session: AsyncSession) -> OperationsSnapshot:
    settings = get_settings()
    rows = (await session.execute(
        select(ConnectorOutbox.status, func.count()).group_by(ConnectorOutbox.status)
    )).all()
    counts = {status: count for status, count in rows}
    oldest = (await session.execute(select(func.min(ConnectorOutbox.created_at)).where(
        ConnectorOutbox.status == "PENDING"
    ))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    oldest_seconds = max(0, int((now - oldest).total_seconds())) if oldest else 0

    latency_rows = (await session.execute(select(Message.latency_ms).where(
        Message.role == "assistant", Message.latency_ms.is_not(None)
    ).order_by(Message.id.desc()).limit(500))).scalars().all()
    totals = []
    for raw in latency_rows:
        try:
            value = json.loads(raw).get("total_ms")
            if isinstance(value, (int, float)):
                totals.append(int(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    p95 = percentile95(totals)
    dead = counts.get("DEAD", 0)
    reasons = []
    if dead >= settings.nova_rollback_dead_jobs_threshold:
        reasons.append(f"dead_jobs={dead}")
    if p95 is not None and p95 > settings.nova_rollback_p95_latency_ms:
        reasons.append(f"p95_latency_ms={p95}")
    return OperationsSnapshot(
        pending_jobs=counts.get("PENDING", 0), processing_jobs=counts.get("PROCESSING", 0),
        dead_jobs=dead, oldest_pending_seconds=oldest_seconds, p95_chat_latency_ms=p95,
        rollout_percent=settings.nova_rollout_percent,
        rollback_recommended=bool(reasons), rollback_reasons=reasons,
    )


async def retention_preview(session: AsyncSession) -> dict[str, int | str]:
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.connector_event_retention_days)
    event_count = (await session.execute(select(func.count()).select_from(ExternalMessageEvent).where(
        ExternalMessageEvent.created_at < cutoff,
        ExternalMessageEvent.status.in_(("PROCESSED", "DEAD")),
    ))).scalar_one()
    link_count = (await session.execute(select(func.count()).select_from(ExternalIdentityLinkCode).where(
        ExternalIdentityLinkCode.expires_at < cutoff,
    ))).scalar_one()
    return {"cutoff": cutoff.isoformat(), "events": event_count, "link_codes": link_count}


async def run_retention(session: AsyncSession) -> dict[str, int]:
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.connector_event_retention_days)
    # Outbox has ON DELETE CASCADE from event; only terminal events are eligible.
    events = await session.execute(delete(ExternalMessageEvent).where(
        ExternalMessageEvent.created_at < cutoff,
        ExternalMessageEvent.status.in_(("PROCESSED", "DEAD")),
    ))
    links = await session.execute(delete(ExternalIdentityLinkCode).where(
        ExternalIdentityLinkCode.expires_at < cutoff,
    ))
    recovered = await recover_stale_outbox(
        session, timeout_seconds=settings.connector_processing_timeout_seconds
    )
    await session.commit()
    return {"events_deleted": events.rowcount or 0, "link_codes_deleted": links.rowcount or 0,
            "stale_jobs_recovered": recovered}


def snapshot_dict(snapshot: OperationsSnapshot) -> dict:
    return asdict(snapshot)
