import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.connectors.common.worker import process_outbox_batch  # noqa: E402
from app.connectors.zalo.handler import process_zalo_outbox  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402


async def main() -> None:
    if not get_settings().zalo_connector_enabled:
        print("ZALO_CONNECTOR_ENABLED=false")
        return
    while True:
        result = await process_outbox_batch(
            AsyncSessionLocal, process_zalo_outbox, limit=10, platform="zalo"
        )
        await asyncio.sleep(0.5 if result["claimed"] else 2)


if __name__ == "__main__":
    asyncio.run(main())
