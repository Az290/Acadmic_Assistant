DISCORD_CONTENT_LIMIT = 2000
SAFE_CHUNK_LIMIT = 1900


def format_discord_reply(answer: str, citations: list[dict], public_web_url: str) -> list[str]:
    text = answer.strip()
    if citations:
        links = []
        for citation in citations[:5]:
            document_id = citation.get("document_id")
            chunk_id = citation.get("chunk_id")
            page = citation.get("page_number")
            label = f"Trang {page}" if page else f"Nguồn {chunk_id}"
            links.append(f"- [{label}]({public_web_url}/documents/{document_id}?chunk={chunk_id})")
        text += "\n\n**Nguồn tham khảo**\n" + "\n".join(links)
    chunks = []
    while text:
        if len(text) <= SAFE_CHUNK_LIMIT:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, SAFE_CHUNK_LIMIT)
        if split_at < SAFE_CHUNK_LIMIT // 2:
            split_at = text.rfind(" ", 0, SAFE_CHUNK_LIMIT)
        if split_at <= 0:
            split_at = SAFE_CHUNK_LIMIT
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip()
    return chunks or ["Nova chưa tạo được câu trả lời."]


def build_discord_message_body(content: str, reply_to_message_id: str | None = None) -> dict:
    body = {
        "content": content[:DISCORD_CONTENT_LIMIT],
        "allowed_mentions": {"parse": [], "replied_user": False},
    }
    if reply_to_message_id:
        body["message_reference"] = {
            "message_id": reply_to_message_id,
            "fail_if_not_exists": False,
        }
    return body
