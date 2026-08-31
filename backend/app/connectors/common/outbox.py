from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConnectorOutbox, ExternalMessageEvent

MAX_OUTBOX_ATTEMPTS = 5


async def recover_stale_outbox(session: AsyncSession, *, timeout_seconds: int = 300) -> int:
    """Tra job ve PENDING neu worker chet sau khi claim nhung truoc khi commit ket qua."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, timeout_seconds))
    result = await session.execute(
        update(ConnectorOutbox)
        .where(ConnectorOutbox.status == "PROCESSING", ConnectorOutbox.locked_at < cutoff)
        .values(status="PENDING", locked_at=None, available_at=datetime.now(timezone.utc),
                last_error="Recovered stale PROCESSING job")
    )
    return result.rowcount or 0


async def claim_outbox(
    session: AsyncSession, limit: int = 10, platform: str | None = None
) -> list[ConnectorOutbox]:
    now = datetime.now(timezone.utc)
    query = select(ConnectorOutbox).where(
        ConnectorOutbox.status == "PENDING", ConnectorOutbox.available_at <= now
    )
    if platform is not None:
        query = query.join(
            ExternalMessageEvent, ExternalMessageEvent.id == ConnectorOutbox.event_id
        ).where(ExternalMessageEvent.platform == platform)
    jobs = list((await session.execute(
        query
        .order_by(ConnectorOutbox.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )).scalars())
    for job in jobs:
        job.status = "PROCESSING"
        job.locked_at = now
        job.attempts += 1
    await session.flush()
    return jobs


def complete_outbox(job: ConnectorOutbox) -> None:
    job.status = "COMPLETED"
    job.completed_at = datetime.now(timezone.utc)
    job.locked_at = None
    # Khong giu noi dung tin nhan sau khi xu ly thanh cong; audit event chi can metadata/hash.
    if hasattr(job, "payload"):
        job.payload = "{}"


def fail_outbox(job: ConnectorOutbox, error: str) -> None:
    job.last_error = error[:2000]
    job.locked_at = None
    if job.attempts >= MAX_OUTBOX_ATTEMPTS:
        job.status = "DEAD"
        return
    job.status = "PENDING"
    job.available_at = datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** job.attempts))
