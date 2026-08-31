from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


LanguagePreference = Literal["auto", "vi", "en"]
DepthPreference = Literal["auto", "beginner", "intermediate", "advanced"]
LengthPreference = Literal["auto", "short", "medium", "detailed"]
ExamplePreference = Literal["auto", "code", "analogy", "step_by_step"]


class PreferencePatch(BaseModel):
    preferred_language: LanguagePreference | None = None
    explanation_depth: DepthPreference | None = None
    response_length: LengthPreference | None = None
    example_style: ExamplePreference | None = None


class PreferencePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    preferred_language: LanguagePreference = "auto"
    explanation_depth: DepthPreference = "auto"
    response_length: LengthPreference = "auto"
    example_style: ExamplePreference = "auto"
    source: Literal["explicit", "inferred"] = "explicit"
    updated_at: datetime | None = None


DEFAULT_PREFERENCE = PreferencePublic()


class MemoryPublic(BaseModel):
    conversation_id: int
    summary: str
    updated_at: datetime | None = None
