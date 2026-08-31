"""Always-on Discord outbox worker."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402
from app.connectors.common.worker import process_outbox_batch  # noqa: E402
from app.connectors.discord.handler import process_discord_outbox  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402


async def run() -> None:
    if not get_settings().discord_connector_enabled:
        raise SystemExit("DISCORD_CONNECTOR_ENABLED=false")
    while True:
        result = await process_outbox_batch(
            AsyncSessionLocal, process_discord_outbox, limit=10, platform="discord"
        )
        await asyncio.sleep(0.25 if result["claimed"] else 2.0)


if __name__ == "__main__":
    asyncio.run(run())
