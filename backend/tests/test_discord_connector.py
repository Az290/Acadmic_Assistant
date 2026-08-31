import unittest

from app.connectors.discord.adapter import normalize_message_create, strip_bot_mention
from app.connectors.discord.formatter import build_discord_message_body, format_discord_reply


def payload(**overrides):
    value = {
        "id": "m1", "channel_id": "c1", "guild_id": "g1",
        "author": {"id": "u1", "bot": False},
        "mentions": [{"id": "nova"}], "content": "<@nova> Python la gi?",
        "timestamp": "2026-08-31T00:00:00+00:00",
    }
    value.update(overrides)
    return value


class DiscordConnectorContractTest(unittest.TestCase):
    def test_group_requires_direct_mention(self):
        self.assertIsNone(normalize_message_create(payload(mentions=[], content="hello"), "nova"))

    def test_dm_does_not_require_mention(self):
        result = normalize_message_create(payload(guild_id=None, mentions=[], content="hello"), "nova")
        self.assertIsNotNone(result)
        self.assertFalse(result.is_group)

    def test_bot_message_is_ignored(self):
        self.assertIsNone(normalize_message_create(payload(author={"id": "u1", "bot": True}), "nova"))

    def test_mention_is_removed_from_question(self):
        self.assertEqual(strip_bot_mention("<@!123> hoc python", "123"), "hoc python")

    def test_reply_suppresses_all_mentions(self):
        body = build_discord_message_body("@everyone <@123>", "m1")
        self.assertEqual(body["allowed_mentions"]["parse"], [])
        self.assertFalse(body["allowed_mentions"]["replied_user"])

    def test_formatter_obeys_discord_limit_and_adds_citation(self):
        chunks = format_discord_reply("word " * 1000, [{"document_id": 1, "chunk_id": 2, "page_number": 3}], "https://app.test")
        self.assertTrue(all(len(chunk) <= 1900 for chunk in chunks))
        self.assertIn("/documents/1?chunk=2", chunks[-1])


if __name__ == "__main__":
    unittest.main()
