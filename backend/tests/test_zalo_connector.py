import unittest

from app.connectors.zalo.adapter import normalize_oa_event, parse_link_command
from app.connectors.zalo.formatter import ZALO_TEXT_LIMIT, build_zalo_message_body, format_zalo_reply


class ZaloConnectorTests(unittest.TestCase):
    def fixture(self, **overrides):
        payload = {
            "event_name": "user_send_text",
            "sender": {"id": "zalo-user-1"},
            "recipient": {"id": "oa-1"},
            "message": {"msg_id": "msg-1", "text": "Python la gi?"},
            "timestamp": 1788100000000,
        }
        payload.update(overrides)
        return payload

    def test_normalizes_private_text(self):
        event = normalize_oa_event(self.fixture())
        self.assertIsNotNone(event)
        self.assertEqual(event.external_user_id, "zalo-user-1")
        self.assertEqual(event.channel_id, "zalo-user-1")
        self.assertFalse(event.is_group)

    def test_unknown_event_and_empty_message_fail_closed(self):
        self.assertIsNone(normalize_oa_event(self.fixture(event_name="user_follow")))
        self.assertIsNone(normalize_oa_event(self.fixture(message={"msg_id": "x", "text": ""})))

    def test_gmf_is_capability_gated(self):
        payload = self.fixture(group={"id": "group-1"}, mentioned_nova=True)
        self.assertIsNone(normalize_oa_event(payload, gmf_enabled=False))
        event = normalize_oa_event(payload, gmf_enabled=True)
        self.assertTrue(event.is_group)
        self.assertEqual(event.channel_id, "group-1")

    def test_formatter_bounds_chunks_and_targets_exact_user(self):
        chunks = format_zalo_reply("a" * (ZALO_TEXT_LIMIT + 10), [], "https://app.test")
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= ZALO_TEXT_LIMIT for chunk in chunks))
        self.assertEqual(build_zalo_message_body("u1", "hi")["recipient"]["user_id"], "u1")

    def test_link_command_is_explicit(self):
        self.assertEqual(parse_link_command("link Abcd_1234"), "Abcd_1234")
        self.assertIsNone(parse_link_command("hay link tai khoan giup toi"))


if __name__ == "__main__":
    unittest.main()
