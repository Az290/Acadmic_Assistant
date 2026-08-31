"""Always-on Discord Gateway process. Mac dinh tat; khong dung self-bot."""

import json
import sys
import time
from pathlib import Path

import discord
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402
from app.connectors.common.security import sign_webhook  # noqa: E402
from app.connectors.discord.adapter import discord_message_to_payload, normalize_message_create  # noqa: E402
from app.connectors.discord.binding import bind_discord_channel  # noqa: E402


def main() -> None:
    settings = get_settings()
    if not settings.discord_connector_enabled:
        raise SystemExit("DISCORD_CONNECTOR_ENABLED=false")
    if not settings.discord_bot_token:
        raise SystemExit("Thieu DISCORD_BOT_TOKEN")
    intents = discord.Intents.none()
    intents.guilds = True
    intents.guild_messages = True
    intents.dm_messages = True
    intents.message_content = False
    client = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(client)
    synced = False

    @tree.command(name="nova-bind", description="Lien ket kenh nay voi mot lop Nova")
    async def nova_bind(interaction: discord.Interaction, course_code: str):
        if interaction.channel_id is None:
            await interaction.response.send_message("Khong xac dinh duoc kenh.", ephemeral=True)
            return
        try:
            await bind_discord_channel(
                external_user_id=str(interaction.user.id),
                channel_id=str(interaction.channel_id),
                course_code=course_code.strip(),
            )
            await interaction.response.send_message(
                f"Da lien ket kenh voi lop `{course_code}`. Nova chi tra loi khi duoc mention.",
                ephemeral=True,
            )
        except (PermissionError, LookupError, ValueError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)

    @client.event
    async def on_ready():
        nonlocal synced
        if not synced:
            await tree.sync()
            synced = True

    @client.event
    async def on_message(message):
        if message.author.bot:
            return
        if message.guild is None and message.content.lower().startswith("link "):
            code = message.content.split(maxsplit=1)[1].strip()
            async with httpx.AsyncClient(timeout=15) as http:
                response = await http.post(
                    f"{settings.discord_internal_api_base.rstrip('/')}/v1/connectors/discord/link",
                    json={"external_user_id": str(message.author.id), "code": code},
                )
            await message.channel.send(
                "Da lien ket Discord voi Nova." if response.is_success
                else "Ma lien ket khong hop le, da het han hoac tai khoan da lien ket danh tinh khac.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        envelope = normalize_message_create(
            discord_message_to_payload(message),
            str(client.user.id) if client.user else (settings.discord_bot_user_id or ""),
        )
        if envelope is None:
            return
        raw = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        secret = settings.connector_webhook_secret or settings.jwt_secret
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.post(
                f"{settings.discord_internal_api_base.rstrip('/')}/v1/connectors/discord/webhook",
                content=raw,
                headers={"Content-Type": "application/json", "X-Nova-Timestamp": timestamp,
                         "X-Nova-Signature": sign_webhook(secret, timestamp, raw)},
            )
            response.raise_for_status()

    client.run(settings.discord_bot_token, log_handler=None)


if __name__ == "__main__":
    main()
