"""Deterministic benchmark Discord adapter, khong can bot token."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.connectors.discord.adapter import normalize_message_create  # noqa: E402
from app.connectors.discord.formatter import build_discord_message_body, format_discord_reply  # noqa: E402

OUT = Path(__file__).parent / "benchmarks" / "results" / "phase7_discord_pilot.json"


def message(**overrides):
    base = {"id": "m1", "channel_id": "c1", "guild_id": "g1", "author": {"id": "u1", "bot": False},
            "mentions": [{"id": "nova"}], "content": "<@nova> Python la gi?", "timestamp": "2026-08-31T00:00:00+00:00"}
    base.update(overrides)
    return base


def main() -> int:
    started = time.perf_counter()
    checks = {
        "group_direct_mention_accepted": normalize_message_create(message(), "nova") is not None,
        "group_without_mention_ignored": normalize_message_create(message(mentions=[], content="hello"), "nova") is None,
        "dm_accepted": normalize_message_create(message(guild_id=None, mentions=[], content="hello"), "nova") is not None,
        "bot_ignored": normalize_message_create(message(author={"id": "u1", "bot": True}), "nova") is None,
        "empty_after_mention_ignored": normalize_message_create(message(content="<@nova>"), "nova") is None,
    }
    body = build_discord_message_body("@everyone hello", "m1")
    checks["allowed_mentions_suppressed"] = body["allowed_mentions"] == {"parse": [], "replied_user": False}
    chunks = format_discord_reply("abc " * 1500, [{"document_id": 1, "chunk_id": 2, "page_number": 3}], "https://app.test")
    checks["all_chunks_within_limit"] = all(len(chunk) <= 1900 for chunk in chunks)
    checks["citation_deep_link"] = "/documents/1?chunk=2" in chunks[-1]
    report = {"summary": {"cases": len(checks), "passed": sum(checks.values()), "pass_rate": sum(checks.values()) / len(checks),
                          "latency_ms": round((time.perf_counter() - started) * 1000, 3)}, "cases": checks}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
