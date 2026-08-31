import hashlib


def is_user_in_rollout(user_id: int, percent: int) -> bool:
    """Stable cohort: same user never flips between legacy/agentic across requests."""
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    bucket = int.from_bytes(hashlib.sha256(f"nova:{user_id}".encode()).digest()[:4], "big") % 100
    return bucket < percent
