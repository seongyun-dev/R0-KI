from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "robot" / "tools" / "diagnose_operations.py"
SPEC = importlib.util.spec_from_file_location("diagnose_operations", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
diagnose = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diagnose
SPEC.loader.exec_module(diagnose)


def publish(
    timestamp: str,
    command_id: str,
    command: str,
    *,
    patrol_id: int | None = None,
    mapping_session_id: int | None = None,
) -> str:
    payload = {
        "schemaVersion": 1,
        "commandId": command_id,
        "command": command,
        "issuedAt": "2026-08-05T21:00:00+09:00",
        "expiresAt": "2026-08-05T21:00:10+09:00",
    }
    if patrol_id is not None:
        payload["patrolId"] = patrol_id
    if mapping_session_id is not None:
        payload["mappingSessionId"] = mapping_session_id
    return (
        f"{timestamp} INFO [MQTT] 발행 완료 "
        "topic=hanbakwi/v1/robots/ROKI-TEST/command, retained=false, payload="
        + json.dumps(payload, separators=(",", ":"))
    )


class DiagnoseOperationsTest(unittest.TestCase):
    def test_start_patrol_publish_and_rejected_ack_are_linked(self) -> None:
        lines = [
            publish(
                "2026-08-05T21:00:00.000+09:00",
                "start-rejected",
                "START_PATROL",
                patrol_id=31,
            ),
            "2026-08-05T21:00:00.250+09:00 INFO [MQTT] 순찰 시작 거절/실패로 "
            "FAILED 처리. patrolId=31, commandId=start-rejected, "
            "status=REJECTED, reason=PATROL_ROUTE_NOT_CONFIGURED",
        ]

        operation = diagnose.parse_operations(lines)[0]

        self.assertEqual(operation.command_id, "start-rejected")
        self.assertEqual(operation.final_result, "REJECTED")
        self.assertEqual(operation.latency_ms, 250.0)
        self.assertEqual(diagnose.classify(operation).layer, "L8_MAP_ROUTE")

    def test_reason_with_equals_is_parsed(self) -> None:
        operation = diagnose.parse_operations(
            [
                "2026-08-05T21:00:00+09:00 INFO 순찰 시작 거절/실패로 FAILED 처리. "
                "patrolId=32, commandId=reason-equals, status=REJECTED, "
                "reason=NAVIGATION_ROUTE_UNSAFE"
            ]
        )[0]
        self.assertEqual(operation.final_reason, "NAVIGATION_ROUTE_UNSAFE")

    def test_reason_without_equals_is_parsed(self) -> None:
        operation = diagnose.parse_operations(
            [
                "2026-08-05T21:00:00+09:00 INFO 순찰 시작 거절/실패로 FAILED 처리. "
                "patrolId=33, commandId=reason-no-equals, status=REJECTED, "
                "reasonNAVIGATION_ROUTE_UNSAFE"
            ]
        )[0]
        self.assertEqual(operation.final_reason, "NAVIGATION_ROUTE_UNSAFE")

    def test_failed_after_succeeded_is_preserved_and_final(self) -> None:
        lines = [
            publish(
                "2026-08-05T21:00:00+09:00",
                "start-late-failure",
                "START_PATROL",
                patrol_id=34,
            ),
            "2026-08-05T21:00:00.100+09:00 INFO [MQTT] 순찰 시작 ACK 처리 완료. "
            "patrolId=34, commandId=start-late-failure",
            "2026-08-05T21:00:01+09:00 INFO [MQTT] 순찰 시작 ACK 처리. "
            "patrolId=34, commandId=start-late-failure, status=FAILED, "
            "reason=RUNTIME_LIFECYCLE_CHANGED",
        ]

        operation = diagnose.parse_operations(lines)[0]

        self.assertEqual([ack.status for ack in operation.acks], ["SUCCEEDED", "FAILED"])
        self.assertEqual(operation.final_result, "FAILED")

    def test_stop_patrol_success_is_parsed(self) -> None:
        lines = [
            publish(
                "2026-08-05T21:00:10+09:00", "stop-36", "STOP_PATROL"
            ),
            "2026-08-05T21:00:10.125+09:00 INFO [MQTT] 순찰 종료 ACK 처리 완료. "
            "patrolId=36, commandId=stop-36",
        ]
        operation = diagnose.parse_operations(lines)[0]
        self.assertEqual(operation.final_result, "SUCCEEDED")
        self.assertEqual(operation.patrol_id, 36)

    def test_stop_failure_with_text_reason_is_classified(self) -> None:
        operation = diagnose.parse_operations(
            [
                "2026-08-05T21:00:10+09:00 WARN [MQTT] 순찰 종료 명령 ACK 처리. "
                "patrolId=36, commandId=stop-failed, status=FAILED, "
                "reason=ESP32 STOP was not delivered"
            ]
        )[0]
        self.assertEqual(operation.final_reason, "ESP32 STOP was not delivered")
        self.assertEqual(diagnose.classify(operation).layer, "L11_STOP_CLEANUP")

    def test_publish_without_ack_is_ack_missing(self) -> None:
        operation = diagnose.parse_operations(
            [
                publish(
                    "2026-08-05T21:00:00+09:00",
                    "missing-ack",
                    "START_MAPPING",
                    mapping_session_id=12,
                )
            ]
        )[0]
        self.assertEqual(operation.final_result, "ACK_MISSING")
        self.assertEqual(operation.linkage, "ACK_MISSING")

    def test_ack_without_publish_is_publish_not_found(self) -> None:
        operation = diagnose.parse_operations(
            [
                "2026-08-05T21:00:01+09:00 INFO [MQTT] 매핑 명령 ACK 처리 완료. "
                "sessionId=12, commandId=missing-publish, status=FAILED, "
                "reason=SLAM_TOOLBOX_NOT_READY"
            ]
        )[0]
        self.assertEqual(operation.linkage, "PUBLISH_NOT_FOUND")
        self.assertEqual(operation.mapping_session_id, 12)

    def test_reason_null_is_unknown(self) -> None:
        operation = diagnose.parse_operations(
            [
                "2026-08-05T21:00:01+09:00 INFO [MQTT] 순찰 시작 거절/실패로 "
                "FAILED 처리. patrolId=30, commandId=null-reason, "
                "status=REJECTED, reason=null"
            ]
        )[0]
        self.assertIsNone(operation.final_reason)
        self.assertEqual(diagnose.classify(operation).layer, "UNKNOWN")

    def test_filters_by_command_id_and_patrol_id(self) -> None:
        operations = diagnose.parse_operations(
            [
                publish(
                    "2026-08-05T21:00:00+09:00",
                    "start-36",
                    "START_PATROL",
                    patrol_id=36,
                ),
                publish(
                    "2026-08-05T21:01:00+09:00",
                    "start-37",
                    "START_PATROL",
                    patrol_id=37,
                ),
            ]
        )
        by_command = diagnose.filter_operations(
            operations,
            operation_type="all",
            command_id="start-36",
            patrol_id=None,
        )
        by_patrol = diagnose.filter_operations(
            operations,
            operation_type="all",
            command_id=None,
            patrol_id=37,
        )
        self.assertEqual([op.command_id for op in by_command], ["start-36"])
        self.assertEqual([op.command_id for op in by_patrol], ["start-37"])

    def test_json_cli_output(self) -> None:
        content = "\n".join(
            [
                publish(
                    "2026-08-05T21:00:00+09:00",
                    "json-start",
                    "START_PATROL",
                    patrol_id=36,
                ),
                "2026-08-05T21:00:00.100+09:00 INFO [MQTT] 순찰 시작 ACK 처리 완료. "
                "patrolId=36, commandId=json-start",
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "backend.log"
            log_path.write_text(content, encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL_PATH),
                    "--file",
                    str(log_path),
                    "--command-id",
                    "json-start",
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = json.loads(completed.stdout)
        self.assertEqual(document["summary"]["totalCommands"], 1)
        self.assertEqual(document["operations"][0]["commandId"], "json-start")

    def test_stdin_cli_output(self) -> None:
        content = publish(
            "2026-08-05T21:00:00+09:00",
            "stdin-mapping",
            "START_MAPPING",
            mapping_session_id=12,
        )
        completed = subprocess.run(
            [sys.executable, str(TOOL_PATH), "--stdin", "--json"],
            input=content,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = json.loads(completed.stdout)
        self.assertEqual(document["operations"][0]["commandId"], "stdin-mapping")

    def test_cli_requires_exactly_one_input_source(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(TOOL_PATH)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--stdin", completed.stderr)
        self.assertIn("--file", completed.stderr)

    def test_set_token_publish_is_excluded(self) -> None:
        line = (
            "2026-08-05T21:00:00+09:00 INFO [MQTT] 발행 완료 topic=test, "
            'payload={"commandId":"token-1","command":"SET_TOKEN"}'
        )
        self.assertEqual(diagnose.parse_operations([line]), [])

    def test_duplicate_ack_count_does_not_remove_timeline(self) -> None:
        first_ack = (
            "2026-08-05T21:00:01+09:00 INFO [MQTT] 순찰 종료 ACK 처리 완료. "
            "patrolId=36, commandId=duplicate-stop"
        )
        second_ack = first_ack.replace("21:00:01", "21:00:02")
        operation = diagnose.parse_operations([first_ack, second_ack])[0]
        self.assertEqual(len(operation.acks), 2)
        self.assertEqual(operation.duplicate_ack_count, 1)


if __name__ == "__main__":
    unittest.main()
