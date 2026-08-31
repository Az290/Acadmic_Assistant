import httpx

from app.connectors.discord.formatter import build_discord_message_body


class DiscordRestClient:
    def __init__(self, token: str, api_base: str = "https://discord.com/api/v10"):
        self.token = token
        self.api_base = api_base.rstrip("/")

    async def send_message(self, channel_id: str, content: str, reply_to: str | None = None) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.api_base}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {self.token}"},
                json=build_discord_message_body(content, reply_to),
            )
            response.raise_for_status()
            return response.json()
