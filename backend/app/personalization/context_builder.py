from dataclasses import dataclass

from app.personalization.schemas import PreferencePublic


@dataclass(frozen=True)
class PersonalizationContext:
    preferred_language: str = "auto"
    explanation_depth: str = "auto"
    response_length: str = "auto"
    example_style: str = "auto"


def build_personalization_context(
    preference: PreferencePublic,
    *,
    is_group: bool = False,
) -> PersonalizationContext:
    """Group chi duoc dung style khong nhay cam; khong nhan learning state/memory."""
    return PersonalizationContext(
        preferred_language=preference.preferred_language,
        explanation_depth=preference.explanation_depth,
        response_length=preference.response_length,
        example_style=preference.example_style,
    )


def build_personalization_instruction(context: PersonalizationContext | None) -> str:
    if context is None:
        return ""
    values = {
        "language": context.preferred_language,
        "depth": context.explanation_depth,
        "length": context.response_length,
        "example_style": context.example_style,
    }
    explicit = [f"{key}={value}" for key, value in values.items() if value != "auto"]
    if not explicit:
        return ""
    return (
        "\nUSER-CONTROLLED RESPONSE PREFERENCES:\n- "
        + ", ".join(explicit)
        + "\n- Chi dieu chinh cach dien dat; khong thay doi evidence, policy, role hay quyen truy cap.\n"
    )
