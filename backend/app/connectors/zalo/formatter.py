from urllib.parse import urlencode


ZALO_TEXT_LIMIT = 1800


def format_zalo_reply(answer: str, citations: list, public_web_url: str) -> list[str]:
    suffixes: list[str] = []
    for citation in citations[:3]:
        document_id = getattr(citation, "document_id", None)
        page = getattr(citation, "page", None)
        if document_id is None and isinstance(citation, dict):
            document_id, page = citation.get("document_id"), citation.get("page")
        if document_id is not None:
            query = urlencode({"document": document_id, "page": page or 1})
            suffixes.append(f"{public_web_url.rstrip('/')}/documents?{query}")
    text = answer.strip()
    if suffixes:
        text += "\n\nNguon tham khao:\n" + "\n".join(suffixes)
    return [text[i:i + ZALO_TEXT_LIMIT] for i in range(0, len(text), ZALO_TEXT_LIMIT)] or [""]


def build_zalo_message_body(user_id: str, text: str) -> dict:
    return {"recipient": {"user_id": user_id}, "message": {"text": text}}
