"""
Voice transcription API - Nhận audio file, gửi qua OpenAI Whisper, trả về text.

Chi phí: $0.006/phút (Whisper API pricing)
Max file: 25MB
Supported formats: mp3, mp4, mpeg, mpga, m4a, wav, webm
"""

import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from openai import OpenAI

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.db.models import AppUser

router = APIRouter(prefix="/v1/voice", tags=["voice"])

# Whisper supported formats
ALLOWED_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/mpeg",
    "audio/x-mpeg",
    "audio/mpga",
    "audio/m4a",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/webm",
    "video/mp4",
}

ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}

# Lazy-loaded OpenAI client
_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=get_settings().openai_api_key)
    return _client


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = None,
    user: AppUser = Depends(get_current_user),
) -> dict:
    """
    Nhận audio file, gửi qua OpenAI Whisper, trả về text đã transcription.

    Args:
        file: Audio file (mp3, mp4, mpeg, mpga, m4a, wav, webm)
        language: Optional language code (e.g., "vi" for Vietnamese)
        user: Authenticated user

    Returns:
        JSON với text, language, duration và cost_estimate

    Chi phí: $0.006/phút audio
    Max file: 25MB
    """
    settings = get_settings()
    max_size_bytes = settings.max_audio_size_mb * 1024 * 1024

    # 1. Validate file exists
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không có file audio nào được gửi.",
        )

    # 2. Validate file extension
    file_ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Định dạng file không được hỗ trợ. Chỉ chấp nhận: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # 3. Validate file size
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File audio trống.",
        )

    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File audio quá lớn. Kích thước tối đa: {settings.max_audio_size_mb}MB.",
        )

    # 4. Validate MIME type if provided
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        # Allow if extension is valid (some browsers don't send correct MIME type)
        pass  # Extension already validated above

    # 5. Call Whisper API
    try:
        client = get_openai_client()

        # Create a file-like object from bytes
        file_content = io.BytesIO(content)
        file_content.name = file.filename

        # Prepare transcription parameters
        params: dict = {
            "model": "whisper-1",
            "file": file_content,
            "response_format": "verbose_json",
        }

        if language:
            params["language"] = language

        # Call Whisper
        response = client.audio.transcriptions.create(**params)

        # 6. Calculate cost estimate
        # Whisper charges $0.006 per minute
        duration_minutes = response.duration / 60 if response.duration else 0
        cost_estimate = duration_minutes * settings.whisper_cost_per_minute

        return {
            "text": response.text,
            "language": response.language,
            "duration": response.duration,
            "cost_estimate": round(cost_estimate, 6),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi transcription audio: {str(e)}",
        )
