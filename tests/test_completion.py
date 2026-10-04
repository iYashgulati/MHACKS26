from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Airlock.completion import DiffSummary, _significance, collect_diff
from Airlock.hook.approval import ApprovalResolution, ApprovalResult
from Airlock.hook.completion import completion_payload
from Airlock.hook.hook import main as hook_main


class SignificanceTests(unittest.TestCase):
    def test_routine_change(self) -> None:
        significance, reasons = _significance(80, 70, ["src/app.ts"])
        self.assertEqual(significance, "routine")
        self.assertEqual(reasons, [])

    def test_sensitive_filename_triggers_review(self) -> None:
        significance, reasons = _significance(1, 0, ["src/auth.ts"])
        self.assertEqual(significance, "review")
        self.assertEqual(reasons, ["touched src/auth.ts"])

    def test_thresholds_are_strict(self) -> None:
        self.assertEqual(_significance(100, 50, ["src/app.ts"])[0], "routine")
        self.assertEqual(_significance(101, 50, ["src/app.ts"])[0], "review")
        self.assertEqual(
            _significance(1, 0, [f"src/file-{i}.ts" for i in range(8)])[0],
            "routine",
        )
        self.assertEqual(
            _significance(1, 0, [f"src/file-{i}.ts" for i in range(9)])[0],
            "review",
        )

    def test_mostly_deletions_rule(self) -> None:
        significance, reasons = _significance(20, 41, ["src/app.ts"])
        self.assertEqual(significance, "review")
        self.assertIn("mostly deletions", reasons)

    def test_collect_diff_includes_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            import subprocess

            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "app.py").write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)

            (root / "app.py").write_text("one\ntwo\n", encoding="utf-8")
            (root / ".env.example").write_text("A=1\nB=2\n", encoding="utf-8")
            summary = collect_diff(root)

            self.assertEqual(summary.added, 3)
            self.assertEqual(summary.removed, 0)
            self.assertEqual(summary.files, (".env.example", "app.py"))


class CompletionHookTests(unittest.TestCase):
    @patch("Airlock.hook.completion.collect_diff")
    def test_stop_payload_uses_deterministic_significance(self, mock_diff) -> None:
        mock_diff.return_value = DiffSummary(200, 10, ("src/app.ts",))
        payload = completion_payload(
            {
                "hook_event_name": "Stop",
                "session_id": "abc",
                "cwd": "/tmp",
                "last_assistant_message": "Implemented the feature.",
                "background_tasks": [],
            }
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["cwd"], "/tmp")
        self.assertEqual(payload["significance"], "review")
        self.assertIn("210 lines changed", payload["reasons"])

    def test_stop_with_background_work_is_not_reported_done(self) -> None:
        payload = completion_payload(
            {"hook_event_name": "Stop", "background_tasks": [{"status": "running"}]}
        )
        self.assertIsNone(payload)

    def test_stop_recovers_final_message_from_older_claude_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "session.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "user", "message": {"content": "check status"}}),
                        json.dumps(
                            {
                                "type": "assistant",
                                "message": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "The build directory does not exist.",
                                        }
                                    ]
                                },
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            payload = completion_payload(
                {
                    "hook_event_name": "Stop",
                    "cwd": directory,
                    "transcript_path": str(transcript),
                }
            )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(
            payload["assistantMessage"],
            "The build directory does not exist.",
        )


class RedirectTests(unittest.TestCase):
    @patch("Airlock.hook.hook.PhotonApprovalProvider.request")
    def test_zero_risk_command_skips_photon_approval(self, request) -> None:
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la | grep build"},
        }

        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(hook_input))), patch("sys.stdout", stdout):
            result = hook_main(
                [
                    "--provider",
                    "claude",
                    "--approval",
                    "photon",
                    "--output",
                    "hook",
                    "--no-audit",
                ]
            )

        self.assertEqual(result, 0)
        request.assert_not_called()
        output = json.loads(stdout.getvalue())["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "allow")

    @patch("Airlock.hook.hook.PhotonApprovalProvider.request")
    def test_redirect_is_returned_to_claude_as_a_denial_reason(self, request) -> None:
        request.return_value = ApprovalResult(
            ApprovalResolution.REDIRECTED,
            "clear node_modules instead",
        )
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf ./build"},
        }

        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(hook_input))), patch("sys.stdout", stdout):
            result = hook_main(
                [
                    "--provider",
                    "claude",
                    "--approval",
                    "photon",
                    "--output",
                    "hook",
                    "--no-audit",
                ]
            )

        self.assertEqual(result, 0)
        output = json.loads(stdout.getvalue())["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn("clear node_modules instead", output["permissionDecisionReason"])
        self.assertIn("Do not retry the original action", output["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
