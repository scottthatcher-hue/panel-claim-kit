import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "panel_claim.py"
CONFIG = ROOT / "examples" / "config.example.json"
RESERVATION = ROOT / "examples" / "reservation-request.json"
DECLINE = ROOT / "examples" / "decline.json"
SELF_LAUNCH_BLOCKED = ROOT / "examples" / "self-launch-blocked.json"


class PanelClaimCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.state = self.dir / "state.json"
        self.run_cli("--state", str(self.state), "init", "--config", str(CONFIG), "--by", "test-registrar")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, expect=0):
        result = subprocess.run(
            [sys.executable, str(CLI), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if expect == 0:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def submit(self, path):
        result = self.run_cli("--state", str(self.state), "submit", "--input", str(path))
        return json.loads(result.stdout)

    def load_state(self):
        return json.loads(self.state.read_text(encoding="utf-8"))

    def test_reservation_can_be_approved_claimed_and_released(self):
        request = self.submit(RESERVATION)
        self.assertEqual(request["status"], "requested")

        approved = json.loads(
            self.run_cli(
                "--state", str(self.state),
                "approve", request["id"],
                "--by", "test-registrar",
                "--claim-if-free",
            ).stdout
        )
        self.assertEqual(approved["status"], "claimed")
        state = self.load_state()
        self.assertEqual(state["machines"]["shared-mac-1"]["active_claim"], request["id"])

        board = self.run_cli("--state", str(self.state), "render-board", "--machine", "shared-mac-1").stdout
        self.assertIn("Review a shared research result", board)
        self.assertNotIn("Registrar-only example details", board)

        released = json.loads(
            self.run_cli(
                "--state", str(self.state),
                "release", request["id"],
                "--by", "test-registrar",
                "--outcome", "Completed in the test harness.",
            ).stdout
        )
        self.assertEqual(released["status"], "released")
        state = self.load_state()
        self.assertIsNone(state["machines"]["shared-mac-1"]["active_claim"])

    def test_decline_is_a_terminal_answer_not_a_request(self):
        request = self.submit(DECLINE)
        self.assertEqual(request["status"], "declined")
        self.assertEqual(request["requested_access"], "none")

    def test_self_launch_without_capability_is_blocked(self):
        request = self.submit(SELF_LAUNCH_BLOCKED)
        self.assertEqual(request["status"], "capability_blocked")
        self.run_cli(
            "--state", str(self.state),
            "approve", request["id"],
            "--by", "test-registrar",
            expect=2,
        )

    def test_self_launch_approval_fails_while_policy_disables_it(self):
        data = json.loads(SELF_LAUNCH_BLOCKED.read_text(encoding="utf-8"))
        data["capabilities"]["can_self_launch"] = True
        path = self.dir / "self-launch-capable.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        request = self.submit(path)
        self.assertEqual(request["status"], "requested")
        self.run_cli(
            "--state", str(self.state),
            "approve", request["id"],
            "--by", "test-registrar",
            expect=2,
        )

    def test_registrar_sets_effective_priority_and_queue_order(self):
        first = self.submit(RESERVATION)
        second_data = json.loads(RESERVATION.read_text(encoding="utf-8"))
        second_data["requester"] = "example-seat-c"
        second_data["requested_access"] = "registrar_launched"
        second_data["public_title"] = "Second queued task"
        second_path = self.dir / "second.json"
        second_path.write_text(json.dumps(second_data), encoding="utf-8")
        second = self.submit(second_path)

        self.run_cli("--state", str(self.state), "approve", first["id"], "--by", "test-registrar", "--effective-priority", "low")
        self.run_cli("--state", str(self.state), "approve", second["id"], "--by", "test-registrar", "--effective-priority", "urgent")
        claimed = json.loads(
            self.run_cli("--state", str(self.state), "claim-next", "--machine", "shared-mac-1", "--by", "test-registrar").stdout
        )
        self.assertEqual(claimed["id"], second["id"])

    def test_expired_claim_releases_machine(self):
        request = self.submit(RESERVATION)
        self.run_cli(
            "--state", str(self.state), "--now", "2026-11-06T17:00:00Z",
            "approve", request["id"], "--by", "test-registrar", "--claim-if-free",
        )
        expired = json.loads(
            self.run_cli(
                "--state", str(self.state), "--now", "2026-11-06T18:00:01Z",
                "expire", "--by", "test-registrar",
            ).stdout
        )
        self.assertEqual(expired["expired"], [request["id"]])
        self.assertIsNone(self.load_state()["machines"]["shared-mac-1"]["active_claim"])

    def test_markdown_intake_parses_to_json(self):
        intake = self.dir / "intake.md"
        intake.write_text(
            """```panel-claim
Requester: example-seat-a
Machine: shared-mac-1
Preference: accept
Requested access: reservation_request
Public title: Parsed from Markdown
Duration minutes: 30
Proposed priority: high
Can request: yes
Can self-launch: no
Can monitor: no
Can release: no
```""",
            encoding="utf-8",
        )
        parsed = json.loads(self.run_cli("parse-markdown", "--input", str(intake)).stdout)
        self.assertEqual(parsed["requester"], "example-seat-a")
        self.assertEqual(parsed["duration_minutes"], 30)
        self.assertFalse(parsed["capabilities"]["can_self_launch"])

    def test_audit_log_records_key_events(self):
        request = self.submit(RESERVATION)
        self.run_cli("--state", str(self.state), "approve", request["id"], "--by", "test-registrar")
        audit_path = self.state.with_suffix(self.state.suffix + ".audit.jsonl")
        events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        actions = {event["action"] for event in events}
        self.assertIn("init", actions)
        self.assertIn("submit", actions)
        self.assertIn("approve", actions)


if __name__ == "__main__":
    unittest.main()
