import dataclasses
import hashlib
import unittest


@dataclasses.dataclass(frozen=True)
class Command:
    epoch: int
    sequence: int
    idempotency_key: str
    expected_state: str
    payload: bytes


class ReferenceLifecycle:
    """Executable golden semantics for A2 server conformance tests."""

    def __init__(self, *, epoch: int, state: str):
        self.epoch = epoch
        self.state = state
        self.next_sequence = 1
        self.applied = {}

    def apply(self, command: Command, *, next_state: str):
        digest = hashlib.sha256(command.payload).hexdigest()
        prior = self.applied.get(command.idempotency_key)
        if prior is not None:
            if prior == (command.sequence, digest):
                return "ALREADY_APPLIED"
            return "IDEMPOTENCY_CONFLICT"
        if command.epoch != self.epoch:
            return "STALE_EPOCH"
        if command.sequence != self.next_sequence:
            return "OUT_OF_ORDER"
        if command.expected_state != self.state:
            return "STATE_CONFLICT"
        self.applied[command.idempotency_key] = (command.sequence, digest)
        self.next_sequence += 1
        self.state = next_state
        return "APPLIED"


class LifecycleSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.lifecycle = ReferenceLifecycle(epoch=7, state="IDLE")
        self.command = Command(7, 1, "begin-1", "IDLE", b"episode-assignment")

    def test_exact_retry_is_already_applied(self):
        self.assertEqual(
            self.lifecycle.apply(self.command, next_state="EPISODE_ACTIVE"),
            "APPLIED",
        )
        self.assertEqual(
            self.lifecycle.apply(self.command, next_state="EPISODE_ACTIVE"),
            "ALREADY_APPLIED",
        )

    def test_same_key_with_different_payload_is_rejected(self):
        self.lifecycle.apply(self.command, next_state="EPISODE_ACTIVE")
        conflicting = dataclasses.replace(self.command, payload=b"changed")
        self.assertEqual(
            self.lifecycle.apply(conflicting, next_state="EPISODE_ACTIVE"),
            "IDEMPOTENCY_CONFLICT",
        )

    def test_stale_epoch_is_rejected_without_state_change(self):
        stale = dataclasses.replace(self.command, epoch=6)
        self.assertEqual(
            self.lifecycle.apply(stale, next_state="EPISODE_ACTIVE"),
            "STALE_EPOCH",
        )
        self.assertEqual(self.lifecycle.state, "IDLE")
        self.assertEqual(self.lifecycle.next_sequence, 1)

    def test_out_of_order_sequence_is_rejected_without_state_change(self):
        future = dataclasses.replace(self.command, sequence=2)
        self.assertEqual(
            self.lifecycle.apply(future, next_state="EPISODE_ACTIVE"),
            "OUT_OF_ORDER",
        )
        self.assertEqual(self.lifecycle.state, "IDLE")

    def test_expected_state_conflict_is_rejected_without_state_change(self):
        conflict = dataclasses.replace(self.command, expected_state="OPENED")
        self.assertEqual(
            self.lifecycle.apply(conflict, next_state="EPISODE_ACTIVE"),
            "STATE_CONFLICT",
        )
        self.assertEqual(self.lifecycle.state, "IDLE")


if __name__ == "__main__":
    unittest.main()
