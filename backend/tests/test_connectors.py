import time
import unittest
from datetime import datetime, timezone

from app.connectors.common.outbox import MAX_OUTBOX_ATTEMPTS, complete_outbox, fail_outbox
from app.connectors.common.schemas import MessageEnvelope
from app.connectors.common.security import hash_link_code, sign_webhook, verify_webhook_signature


class FakeJob:
    def __init__(self, attempts: int):
        self.attempts = attempts
        self.status = "PROCESSING"
        self.last_error = None
        self.locked_at = datetime.now(timezone.utc)
        self.available_at = datetime.now(timezone.utc)
        self.completed_at = None


class ConnectorContractTest(unittest.TestCase):
    def test_link_code_is_hashed_deterministically(self):
        self.assertEqual(len(hash_link_code("secret-code")), 64)
        self.assertNotIn("secret-code", hash_link_code("secret-code"))

    def test_webhook_signature_and_body_tamper(self):
        now = int(time.time())
        timestamp = str(now)
        body = b'{"event":"1"}'
        signature = sign_webhook("secret", timestamp, body)
        self.assertTrue(verify_webhook_signature(
            secret="secret", timestamp=timestamp, body=body, signature=signature, now=now
        ))
        self.assertFalse(verify_webhook_signature(
            secret="secret", timestamp=timestamp, body=b'{"event":"2"}', signature=signature, now=now
        ))

    def test_webhook_replay_window(self):
        old = str(int(time.time()) - 301)
        signature = sign_webhook("secret", old, b"body")
        self.assertFalse(verify_webhook_signature(
            secret="secret", timestamp=old, body=b"body", signature=signature
        ))

    def test_envelope_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            MessageEnvelope(
                external_event_id="evt", external_user_id="u", channel_id="c",
                is_group=True, mentioned_nova=True, text="", timestamp=datetime.now(timezone.utc),
            )

    def test_outbox_retry_and_dead_letter(self):
        retry = FakeJob(1)
        fail_outbox(retry, "temporary")
        self.assertEqual(retry.status, "PENDING")
        dead = FakeJob(MAX_OUTBOX_ATTEMPTS)
        fail_outbox(dead, "permanent")
        self.assertEqual(dead.status, "DEAD")

    def test_outbox_complete(self):
        job = FakeJob(1)
        complete_outbox(job)
        self.assertEqual(job.status, "COMPLETED")
        self.assertIsNotNone(job.completed_at)


if __name__ == "__main__":
    unittest.main()
