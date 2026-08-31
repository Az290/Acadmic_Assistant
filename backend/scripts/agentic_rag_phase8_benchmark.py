import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.zalo.adapter import normalize_oa_event, parse_link_command  # noqa: E402
from app.connectors.zalo.formatter import ZALO_TEXT_LIMIT, format_zalo_reply  # noqa: E402


def main() -> None:
    base = {"event_name": "user_send_text", "sender": {"id": "student-zalo"},
            "recipient": {"id": "oa"}, "message": {"msg_id": "m1", "text": "Python la gi?"},
            "timestamp": 1788100000000}
    checks = {
        "oa_text_normalized": normalize_oa_event(base) is not None,
        "unknown_event_ignored": normalize_oa_event({**base, "event_name": "user_follow"}) is None,
        "missing_id_ignored": normalize_oa_event({**base, "message": {"text": "x"}}) is None,
        "gmf_disabled": normalize_oa_event({**base, "group": {"id": "g1"}}) is None,
        "gmf_explicit_gate": normalize_oa_event({**base, "group": {"id": "g1"}}, gmf_enabled=True) is not None,
        "explicit_link_command": parse_link_command("link Abcd_1234") == "Abcd_1234",
        "link_false_positive_blocked": parse_link_command("link tai khoan") is None,
        "outbound_bounded": all(len(x) <= ZALO_TEXT_LIMIT for x in format_zalo_reply("x" * 4000, [], "https://app")),
    }
    score = sum(checks.values())
    print(json.dumps({"phase": 8, "score": score, "total": len(checks), "checks": checks}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if score == len(checks) else 1)


if __name__ == "__main__":
    main()
