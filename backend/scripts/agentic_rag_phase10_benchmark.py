import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.connectors.common.outbox import complete_outbox, fail_outbox  # noqa: E402
from app.connectors.common.security import sign_webhook, verify_webhook_signature  # noqa: E402
from app.operations.service import percentile95  # noqa: E402
from app.operations.rollout import is_user_in_rollout  # noqa: E402


def main() -> int:
    body, secret, timestamp = b'{"event":"x"}', "secret", "1788100000"
    signature = sign_webhook(secret, timestamp, body)
    completed = SimpleNamespace(status="PROCESSING", completed_at=None, locked_at=datetime.now(timezone.utc), payload="private")
    complete_outbox(completed)
    retry = SimpleNamespace(status="PROCESSING", attempts=1, last_error=None, locked_at=datetime.now(timezone.utc), available_at=None)
    fail_outbox(retry, "temporary")
    dead = SimpleNamespace(status="PROCESSING", attempts=5, last_error=None, locked_at=datetime.now(timezone.utc), available_at=None)
    fail_outbox(dead, "fatal")
    settings = get_settings()
    checks = {
        "signature_valid": verify_webhook_signature(secret=secret, timestamp=timestamp, body=body, signature=signature, now=1788100000),
        "signature_replay_blocked": not verify_webhook_signature(secret=secret, timestamp=timestamp, body=body, signature=signature, now=1788100301),
        "completed_payload_redacted": completed.status == "COMPLETED" and completed.payload == "{}",
        "temporary_failure_retried": retry.status == "PENDING" and retry.last_error == "temporary",
        "max_attempts_dead_letter": dead.status == "DEAD",
        "p95_correct": percentile95(list(range(1, 101))) == 95,
        "retention_positive": settings.connector_event_retention_days > 0,
        "rollout_bounded": 0 <= settings.nova_rollout_percent <= 100,
        "rollout_zero_and_full": not is_user_in_rollout(1, 0) and is_user_in_rollout(1, 100),
        "rollout_stable": is_user_in_rollout(42, 25) == is_user_in_rollout(42, 25),
        "external_connectors_default_off": not settings.discord_connector_enabled and not settings.zalo_connector_enabled,
    }
    print(json.dumps({"phase": 10, "passed": sum(checks.values()), "total": len(checks), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
