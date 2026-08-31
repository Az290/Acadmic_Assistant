import httpx

from app.connectors.zalo.formatter import build_zalo_message_body


class ZaloOARestClient:
    def __init__(self, access_token: str, api_base: str = "https://openapi.zalo.me/v3.0/oa"):
        self.access_token = access_token
        self.api_base = api_base.rstrip("/")

    async def send_text(self, user_id: str, text: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.api_base}/message/cs",
                headers={"access_token": self.access_token, "Content-Type": "application/json"},
                json=build_zalo_message_body(user_id, text),
            )
            response.raise_for_status()
            data = response.json()
            if data.get("error") not in (None, 0):
                raise RuntimeError(f"Zalo OA API error={data.get('error')}")
            return data
