from datetime import datetime, timezone
import re

from app.connectors.common.schemas import MessageEnvelope


SUPPORTED_TEXT_EVENTS = {"user_send_text", "oa_user_send_text"}
LINK_COMMAND = re.compile(r"^link\s+([A-Za-z0-9_-]{8,100})$", re.IGNORECASE)


def parse_link_command(text: str) -> str | None:
    match = LINK_COMMAND.fullmatch(text.strip())
    return match.group(1) if match else None


def _id(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or value.get("user_id") or "")
    return str(value or "")


def normalize_oa_event(payload: dict, *, gmf_enabled: bool = False) -> MessageEnvelope | None:
    """Normalize only inbound text events; unknown Zalo events fail closed.

    GMF payloads are intentionally rejected until the OA/App has that capability.
    The adapter accepts small field aliases so recorded provider fixtures can be
    replayed across OA webhook versions without weakening identity boundaries.
    """
    event_name = str(payload.get("event_name") or payload.get("event") or "")
    if event_name not in SUPPORTED_TEXT_EVENTS:
        return None
    message = payload.get("message") or {}
    text = str(message.get("text") or payload.get("text") or "").strip()
    sender_id = _id(payload.get("sender") or payload.get("user_id"))
    recipient_id = _id(payload.get("recipient"))
    group_id = _id(payload.get("group") or payload.get("group_id"))
    is_group = bool(group_id)
    if is_group and not gmf_enabled:
        return None
    if not text or not sender_id:
        return None
    event_id = str(
        message.get("msg_id") or payload.get("event_id") or payload.get("message_id") or ""
    )
    if not event_id:
        return None
    raw_timestamp = payload.get("timestamp")
    if isinstance(raw_timestamp, (int, float)):
        seconds = raw_timestamp / 1000 if raw_timestamp > 10_000_000_000 else raw_timestamp
        timestamp = datetime.fromtimestamp(seconds, tz=timezone.utc)
    else:
        timestamp = raw_timestamp or datetime.now(timezone.utc).isoformat()
    return MessageEnvelope(
        external_event_id=event_id,
        external_user_id=sender_id,
        channel_id=group_id or sender_id,
        thread_id=group_id or recipient_id,
        is_group=is_group,
        mentioned_nova=not is_group or bool(payload.get("mentioned_nova")),
        text=text,
        timestamp=timestamp,
    )


def oa_event_to_payload(envelope: MessageEnvelope) -> dict:
    return envelope.model_dump(mode="json")
