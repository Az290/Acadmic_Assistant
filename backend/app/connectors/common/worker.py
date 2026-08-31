import json
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.connectors.common.outbox import claim_outbox, complete_outbox, fail_outbox
from app.db.models import ConnectorOutbox, ExternalMessageEvent

OutboxHandler = Callable[[dict], Awaitable[None]]


async def process_outbox_batch(
    session_factory: async_sessionmaker[AsyncSession], handler: OutboxHandler, limit: int = 10,
    platform: str | None = None,
) -> dict[str, int]:
    """Claim atomically, commit lock state, then process each job in its own transaction."""
    async with session_factory() as session:
        claimed = await claim_outbox(session, limit=limit, platform=platform)
        job_ids = [job.id for job in claimed]
        await session.commit()
    completed = failed = dead = 0
    for job_id in job_ids:
        async with session_factory() as session:
            job = await session.get(ConnectorOutbox, job_id, with_for_update=True)
            if job is None or job.status != "PROCESSING":
                continue
            event = await session.get(ExternalMessageEvent, job.event_id, with_for_update=True)
            try:
                await handler(json.loads(job.payload))
                complete_outbox(job)
                if event:
                    event.status = "PROCESSED"
                    event.processed_at = job.completed_at
                completed += 1
            except Exception as exc:
                fail_outbox(job, f"{type(exc).__name__}: {exc}")
                if event:
                    event.status = "DEAD" if job.status == "DEAD" else "RETRY"
                    event.retry_count = job.attempts
                    event.error = job.last_error
                dead += job.status == "DEAD"
                failed += job.status != "DEAD"
            await session.commit()
    return {"claimed": len(job_ids), "completed": completed, "failed": failed, "dead": dead}
