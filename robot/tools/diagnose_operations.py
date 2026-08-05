#!/usr/bin/env python3
"""Read-only Mapping/Patrol command diagnostics for Backend log text."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, TextIO


COMMANDS = {"START_MAPPING", "START_PATROL", "STOP_PATROL"}
ACK_STATUSES = {"SUCCEEDED", "REJECTED", "FAILED"}


@dataclass
class AckEvent:
    timestamp: str | None
    status: str
    reason: str | None
    line_number: int


@dataclass
class Operation:
    command_id: str
    command: str | None = None
    publish_timestamp: str | None = None
    mapping_session_id: int | None = None
    patrol_id: int | None = None
    issued_at: str | None = None
    expires_at: str | None = None
    publish_line_number: int | None = None
    acks: list[AckEvent] = field(default_factory=list)

    @property
    def operation_type(self) -> str:
        return "mapping" if self.command == "START_MAPPING" else "patrol"

    @property
    def ack_timestamp(self) -> str | None:
        return self.acks[-1].timestamp if self.acks else None

    @property
    def final_result(self) -> str:
        if not self.acks:
            return "ACK_MISSING"
        if any(ack.status == "FAILED" for ack in self.acks):
            return "FAILED"
        return self.acks[-1].status

    @property
    def final_reason(self) -> str | None:
        candidates = [
            ack for ack in self.acks if ack.status == self.final_result
        ]
        if not candidates:
            candidates = self.acks
        return candidates[-1].reason if candidates else None

    @property
    def linkage(self) -> str:
        if self.publish_timestamp is None and self.publish_line_number is None:
            return "PUBLISH_NOT_FOUND"
        if not self.acks:
            return "ACK_MISSING"
        return "LINKED"

    @property
    def duplicate_ack_count(self) -> int:
        signatures = {(ack.status, ack.reason) for ack in self.acks}
        return max(0, len(self.acks) - len(signatures))

    @property
    def latency_ms(self) -> float | None:
        published = parse_datetime(self.publish_timestamp)
        acknowledged = parse_datetime(self.ack_timestamp)
        if published is None or acknowledged is None:
            return None
        return round((acknowledged - published).total_seconds() * 1000, 3)


@dataclass(frozen=True)
class Classification:
    layer: str
    meaning: str
    check: str


CLASSIFICATIONS: dict[str, Classification] = {
    "SLAM_TOOLBOX_NOT_READY": Classification(
        "L8_MAPPING_SLAM",
        "SLAM Toolbox 준비 실패",
        "Jetson의 SLAM lifecycle 및 map exporter readiness 확인",
    ),
    "RUNTIME_LIFECYCLE_CHANGED": Classification(
        "L5_RUNTIME",
        "명령 처리 중 Runtime lifecycle 변경",
        "중복 Mapping/Patrol과 cleanup 상태 확인",
    ),
    "PATROL_ROUTE_NOT_CONFIGURED": Classification(
        "L8_MAP_ROUTE",
        "순찰 경로 또는 waypoint 미설정",
        "현재 map version의 waypoint와 마지막 DESTINATION 확인",
    ),
    "NAVIGATION_ROUTE_UNSAFE": Classification(
        "L8_MAP_ROUTE",
        "순찰 경로 안전성 검사 실패",
        "waypoint 좌표, map bounds, waypoint 간 거리와 clearance 확인",
    ),
    "NAV2_ACTION_SERVER_NOT_READY": Classification(
        "L8_NAV2",
        "NavigateToPose action server 준비 실패",
        "Nav2 lifecycle과 /navigate_to_pose action server 확인",
    ),
    "LIDAR_NOT_READY": Classification(
        "L7_SENSOR", "LiDAR 준비 실패", "/scan freshness와 LiDAR 상태 확인"
    ),
    "SCAN_TIMEOUT": Classification(
        "L7_SENSOR", "/scan timeout", "/scan freshness와 LiDAR 상태 확인"
    ),
    "ODOMETRY_NOT_READY": Classification(
        "L7_ODOMETRY", "Odometry 준비 실패", "/odom freshness 확인"
    ),
    "ODOM_TIMEOUT": Classification(
        "L7_ODOMETRY", "Odometry timeout", "/odom freshness 확인"
    ),
    "MAP_POSE_NOT_READY": Classification(
        "L7_LOCALIZATION",
        "Map pose 준비 실패",
        "map→odom→base_link TF와 AMCL pose 확인",
    ),
    "TF_UNAVAILABLE": Classification(
        "L7_LOCALIZATION",
        "필수 TF 없음",
        "map→odom→base_link TF와 AMCL pose 확인",
    ),
    "LOCALIZATION_NOT_READY": Classification(
        "L7_LOCALIZATION",
        "Localization 준비 실패",
        "map→odom→base_link TF와 AMCL pose 확인",
    ),
    "COMMAND_EXPIRED": Classification(
        "L4_COMMAND",
        "명령 TTL 만료",
        "issuedAt, expiresAt과 publish/ACK latency 확인",
    ),
    "DUPLICATE_PAYLOAD_MISMATCH": Classification(
        "L4_COMMAND",
        "동일 commandId의 payload 불일치",
        "같은 commandId를 다른 payload에 재사용했는지 확인",
    ),
    "FIRST_GOAL_REJECTED": Classification(
        "L9_FIRST_GOAL",
        "첫 Nav2 goal 거절",
        "첫 Nav2 goal response와 action server 상태 확인",
    ),
    "NAV2_GOAL_REJECTED": Classification(
        "L9_FIRST_GOAL",
        "첫 Nav2 goal 거절",
        "첫 Nav2 goal response와 action server 상태 확인",
    ),
    "FIRST_GOAL_TIMEOUT": Classification(
        "L9_FIRST_GOAL",
        "첫 Nav2 goal acceptance timeout",
        "첫 Nav2 goal response와 action server 상태 확인",
    ),
    "NAV2_FIRST_GOAL_ACCEPT_TIMEOUT": Classification(
        "L9_FIRST_GOAL",
        "첫 Nav2 goal acceptance timeout",
        "첫 Nav2 goal response와 action server 상태 확인",
    ),
    "PATROL_ALREADY_ACTIVE": Classification(
        "L5_RUNTIME",
        "이미 순찰 실행 중",
        "active operation과 cleanup 완료 여부 확인",
    ),
    "MAPPING_ACTIVE": Classification(
        "L5_RUNTIME",
        "Mapping 실행 중",
        "active operation과 cleanup 완료 여부 확인",
    ),
    "RUNTIME_NOT_READY": Classification(
        "L5_RUNTIME",
        "Runtime 준비 실패",
        "active operation과 cleanup 완료 여부 확인",
    ),
}

UNKNOWN = Classification(
    "UNKNOWN",
    "원인 정보가 없거나 분류표에 없는 실패",
    "동일 commandId의 Jetson Robot 로그 확인",
)
SUCCESS = Classification("-", "명령 ACK 성공", "추가 실패 확인 불필요")
ACK_MISSING = Classification(
    "L2_BACKEND_COMMAND",
    "발행 후 ACK를 찾지 못함",
    "동일 commandId의 Backend·Broker·Jetson 로그 확인",
)


TIMESTAMP_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?)"
)
FIELD_PATTERNS = {
    name: re.compile(rf"\b{name}\s*[=:]\s*([^,\s\]\}}]+)")
    for name in (
        "commandId",
        "command",
        "mappingSessionId",
        "sessionId",
        "patrolId",
        "issuedAt",
        "expiresAt",
        "status",
    )
}
REASON_RE = re.compile(
    r"(?:^|[\s,])reason(?:\s*=\s*([^,\]\}}]+)|([A-Z][A-Z0-9_:.-]*))"
)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace(",", ".")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def timestamp_from_line(line: str) -> str | None:
    match = TIMESTAMP_RE.search(line)
    return match.group("ts") if match else None


def field_from_line(line: str, name: str) -> str | None:
    match = FIELD_PATTERNS[name].search(line)
    return match.group(1).strip('"') if match else None


def integer_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_reason(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().strip('"')
    if normalized.lower() in {"", "null", "none", "-"}:
        return None
    return normalized


def json_payload_from_publish(line: str) -> dict[str, Any] | None:
    lowered = line.lower()
    payload_marker = lowered.find("payload=")
    explicit_publish = "발행 완료" in line or "publish" in lowered
    command_topic_log = (
        payload_marker >= 0
        and "/command" in lowered
        and "/command/ack" not in lowered
    )
    if not explicit_publish and not command_topic_log:
        return None
    search_from = payload_marker + len("payload=") if payload_marker >= 0 else 0
    object_start = line.find("{", search_from)
    if object_start < 0:
        return None
    try:
        decoded, _end = json.JSONDecoder().raw_decode(line[object_start:])
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict) or decoded.get("command") not in COMMANDS:
        return None
    return decoded


PATROL_START_SUCCESS_MESSAGE = "순찰 시작 ACK 처리 완료"
PATROL_STOP_SUCCESS_MESSAGE = "순찰 종료 ACK 처리 완료"
MAPPING_ACK_MESSAGE = "매핑 명령 ACK 처리 완료"


def infer_ack_command(
    line: str, correlated_command: str | None = None
) -> str | None:
    explicit = field_from_line(line, "command")
    if explicit in COMMANDS:
        return explicit
    if "매핑 명령 ACK" in line or "START_MAPPING" in line:
        return "START_MAPPING"
    if "순찰 시작" in line or "START_PATROL" in line:
        return "START_PATROL"
    if "순찰 종료" in line or "STOP_PATROL" in line:
        return "STOP_PATROL"
    if correlated_command in COMMANDS:
        return correlated_command
    # Windows PowerShell 5 native pipelines can replace Korean output from
    # ssh with '?'. Keep this as a narrow fallback for ACK-only log input;
    # commandId correlation above remains the preferred path.
    if "MappingCommandAckService" in line:
        return "START_MAPPING"
    return None


def infer_ack_status(
    line: str,
    *,
    command: str | None,
    correlated_command: str | None,
) -> str | None:
    explicit = field_from_line(line, "status")
    if explicit in ACK_STATUSES:
        return explicit
    if PATROL_START_SUCCESS_MESSAGE in line or PATROL_STOP_SUCCESS_MESSAGE in line:
        return "SUCCEEDED"
    if "순찰 시작 거절/실패로 FAILED 처리" in line:
        return "FAILED"
    # The two Patrol success messages above become the same
    # "?? ?? ACK ?? ??." text in Windows PowerShell 5. Only infer success
    # when the line is still a Patrol ACK-service record and commandId already
    # correlated it to a published START/STOP command. This does not turn an
    # arbitrary ACK line into success.
    if (
        correlated_command in {"START_PATROL", "STOP_PATROL"}
        and command == correlated_command
        and "PatrolCommandAckService" in line
        and "[MQTT]" in line
        and " ACK " in line
    ):
        return "SUCCEEDED"
    return None


def reason_from_line(line: str) -> str | None:
    match = REASON_RE.search(line)
    if match is None:
        return None
    return normalize_reason(match.group(1) or match.group(2))


def parse_operations(lines: Iterable[str]) -> list[Operation]:
    operations: dict[str, Operation] = {}
    for line_number, line in enumerate(lines, start=1):
        payload = json_payload_from_publish(line)
        if payload is not None:
            command_id = payload.get("commandId")
            if not isinstance(command_id, str) or not command_id:
                continue
            operation = operations.setdefault(command_id, Operation(command_id))
            operation.command = str(payload["command"])
            operation.publish_timestamp = timestamp_from_line(line)
            operation.publish_line_number = line_number
            operation.mapping_session_id = integer_or_none(
                payload.get("mappingSessionId")
            )
            operation.patrol_id = integer_or_none(payload.get("patrolId"))
            operation.issued_at = payload.get("issuedAt")
            operation.expires_at = payload.get("expiresAt")
            continue

        if (
            "ACK" not in line
            and "ack=" not in line.lower()
            and field_from_line(line, "status") not in ACK_STATUSES
            and "순찰 시작 거절/실패로 FAILED 처리" not in line
        ):
            continue
        command_id = field_from_line(line, "commandId")
        existing = operations.get(command_id) if command_id else None
        correlated_command = existing.command if existing is not None else None
        command = infer_ack_command(line, correlated_command)
        status = infer_ack_status(
            line,
            command=command,
            correlated_command=correlated_command,
        )
        if not command_id or command not in COMMANDS or status not in ACK_STATUSES:
            continue
        operation = operations.setdefault(command_id, Operation(command_id))
        operation.command = operation.command or command
        mapping_id = field_from_line(line, "mappingSessionId") or field_from_line(
            line, "sessionId"
        )
        patrol_id = field_from_line(line, "patrolId")
        operation.mapping_session_id = (
            operation.mapping_session_id or integer_or_none(mapping_id)
        )
        operation.patrol_id = operation.patrol_id or integer_or_none(patrol_id)
        operation.acks.append(
            AckEvent(
                timestamp=timestamp_from_line(line),
                status=status,
                reason=reason_from_line(line),
                line_number=line_number,
            )
        )

    return sorted(operations.values(), key=operation_sort_key)


def operation_sort_key(operation: Operation) -> tuple[float, int]:
    timestamp = operation.publish_timestamp or operation.ack_timestamp
    parsed = parse_datetime(timestamp)
    return (
        parsed.timestamp() if parsed is not None else float("-inf"),
        operation.publish_line_number or 0,
    )


def classify(operation: Operation) -> Classification:
    if operation.final_result == "ACK_MISSING":
        return ACK_MISSING
    if operation.final_result == "SUCCEEDED":
        return SUCCESS
    reason = operation.final_reason
    if reason is None:
        return UNKNOWN
    normalized = reason.upper()
    if "STOP" in normalized and (
        "FAILED" in normalized
        or "FAILURE" in normalized
        or "UNCONFIRMED" in normalized
        or "NOT DELIVERED" in normalized
        or "TIMEOUT" in normalized
    ):
        return Classification(
            "L11_STOP_CLEANUP",
            "STOP 또는 cleanup 실패",
            "Nav2 cancel, zero motion, Serial STOP, AI disable, cleanup 로그 확인",
        )
    if normalized.startswith("COMMAND_EXPIRED"):
        return CLASSIFICATIONS["COMMAND_EXPIRED"]
    return CLASSIFICATIONS.get(normalized, UNKNOWN)


def filter_operations(
    operations: Iterable[Operation],
    *,
    operation_type: str,
    command_id: str | None,
    patrol_id: int | None,
) -> list[Operation]:
    result = []
    for operation in operations:
        if operation_type != "all" and operation.operation_type != operation_type:
            continue
        if command_id is not None and operation.command_id != command_id:
            continue
        if patrol_id is not None and operation.patrol_id != patrol_id:
            continue
        result.append(operation)
    return result


def summary(operations: list[Operation]) -> dict[str, Any]:
    results = Counter(operation.final_result for operation in operations)
    reasons = Counter(
        operation.final_reason or "UNKNOWN"
        for operation in operations
        if operation.final_result not in {"SUCCEEDED", "ACK_MISSING"}
    )
    return {
        "totalCommands": len(operations),
        "mappingStarts": sum(op.command == "START_MAPPING" for op in operations),
        "patrolStarts": sum(op.command == "START_PATROL" for op in operations),
        "patrolStops": sum(op.command == "STOP_PATROL" for op in operations),
        "results": {
            name: results.get(name, 0)
            for name in ("SUCCEEDED", "REJECTED", "FAILED", "ACK_MISSING")
        },
        "reasons": dict(sorted(reasons.items())),
    }


def diagnostic_summary(operations: list[Operation]) -> dict[str, Any]:
    failed_layers = Counter(
        classify(operation).layer
        for operation in operations
        if operation.final_result != "SUCCEEDED"
    )
    most_common_layer = failed_layers.most_common(1)[0][0] if failed_layers else None
    successful_starts = [
        operation
        for operation in operations
        if operation.command == "START_PATROL"
        and operation.final_result == "SUCCEEDED"
    ]
    stops_by_patrol = {
        operation.patrol_id
        for operation in operations
        if operation.command == "STOP_PATROL" and operation.patrol_id is not None
    }
    starts_without_stop = [
        operation.command_id
        for operation in successful_starts
        if operation.patrol_id not in stops_by_patrol
    ]
    return {
        "mostFrequentFailureLayer": most_common_layer,
        "ackMissing": sum(op.final_result == "ACK_MISSING" for op in operations),
        "reasonNull": sum(
            op.final_result not in {"SUCCEEDED", "ACK_MISSING"}
            and op.final_reason is None
            for op in operations
        ),
        "successfulPatrolStarts": len(successful_starts),
        "successfulStartsWithoutStop": starts_without_stop,
        "completionNotice": (
            "Backend 로그만으로 정상 완주 COMPLETED 여부를 단정할 수 없습니다."
        ),
    }


def operation_as_json(operation: Operation) -> dict[str, Any]:
    classification = classify(operation)
    return {
        "operationId": operation.command_id,
        "command": operation.command,
        "commandId": operation.command_id,
        "mappingSessionId": operation.mapping_session_id,
        "patrolId": operation.patrol_id,
        "publishTimestamp": operation.publish_timestamp,
        "ackTimestamp": operation.ack_timestamp,
        "issuedAt": operation.issued_at,
        "expiresAt": operation.expires_at,
        "latencyMs": operation.latency_ms,
        "ackTimeline": [asdict(ack) for ack in operation.acks],
        "duplicateAckCount": operation.duplicate_ack_count,
        "linkage": operation.linkage,
        "finalResult": operation.final_result,
        "reason": operation.final_reason or (
            "UNKNOWN" if operation.final_result != "SUCCEEDED" else None
        ),
        "layer": classification.layer,
        "meaning": classification.meaning,
        "check": classification.check,
    }


def render_json(operations: list[Operation], output: TextIO) -> None:
    document = {
        "summary": summary(operations),
        "operations": [operation_as_json(operation) for operation in operations],
        "diagnostics": diagnostic_summary(operations),
    }
    json.dump(document, output, ensure_ascii=False, indent=2)
    output.write("\n")


def render_text(operations: list[Operation], output: TextIO) -> None:
    top = summary(operations)
    output.write("=== Mapping·Patrol 명령 진단 요약 ===\n")
    output.write(
        f"전체 {top['totalCommands']} | Mapping START {top['mappingStarts']} | "
        f"Patrol START {top['patrolStarts']} | Patrol STOP {top['patrolStops']}\n"
    )
    output.write(
        "결과 "
        + " | ".join(f"{key} {value}" for key, value in top["results"].items())
        + "\n"
    )
    reasons = top["reasons"]
    output.write(
        "reason "
        + (", ".join(f"{key}={value}" for key, value in reasons.items()) or "없음")
        + "\n\n"
    )

    for index, operation in enumerate(operations, start=1):
        item = operation_as_json(operation)
        output.write(f"[{index}] {item['command']} / {item['commandId']}\n")
        output.write(
            f"  mappingSessionId={item['mappingSessionId'] or '-'} "
            f"patrolId={item['patrolId'] or '-'} linkage={item['linkage']}\n"
        )
        output.write(
            f"  publish={item['publishTimestamp'] or '-'} "
            f"ack={item['ackTimestamp'] or '-'} latencyMs="
            f"{item['latencyMs'] if item['latencyMs'] is not None else '-'}\n"
        )
        output.write(
            f"  issuedAt={item['issuedAt'] or '-'} expiresAt={item['expiresAt'] or '-'}\n"
        )
        if operation.acks:
            for ack_index, ack in enumerate(operation.acks, start=1):
                output.write(
                    f"  ACK#{ack_index} {ack.timestamp or '-'} {ack.status} "
                    f"reason={ack.reason or 'UNKNOWN'}\n"
                )
        else:
            output.write("  ACK timeline: 없음\n")
        output.write(
            f"  final={item['finalResult']} reason={item['reason'] or '-'} "
            f"duplicateACK={item['duplicateAckCount']}\n"
        )
        output.write(f"  layer={item['layer']} meaning={item['meaning']}\n")
        output.write(f"  check={item['check']}\n\n")

    diagnostics = diagnostic_summary(operations)
    output.write("=== 종합 진단 ===\n")
    output.write(
        "최다 실패 계층: "
        f"{diagnostics['mostFrequentFailureLayer'] or '없음'}\n"
    )
    output.write(f"ACK 없는 명령: {diagnostics['ackMissing']}\n")
    output.write(f"reason=null/없음: {diagnostics['reasonNull']}\n")
    output.write(
        "START_PATROL 성공 후 STOP 없는 commandId: "
        + (
            ", ".join(diagnostics["successfulStartsWithoutStop"])
            if diagnostics["successfulStartsWithoutStop"]
            else "없음"
        )
        + "\n"
    )
    output.write(diagnostics["completionNotice"] + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backend 로그에서 Mapping·Patrol MQTT command/ACK를 읽기 전용으로 연결합니다."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--stdin", action="store_true", help="표준 입력 로그 분석")
    source.add_argument("--file", type=Path, help="UTF-8 로그 파일 분석")
    parser.add_argument("--command-id", help="특정 commandId만 출력")
    parser.add_argument("--patrol-id", type=int, help="특정 patrolId만 출력")
    parser.add_argument(
        "--operation",
        choices=("all", "mapping", "patrol"),
        default="all",
        help="분석 operation 종류 (기본: all)",
    )
    parser.add_argument("--json", action="store_true", help="JSON 형식 출력")
    return parser


def configure_utf8() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def read_input(args: argparse.Namespace) -> list[str]:
    if args.stdin:
        return sys.stdin.readlines()
    try:
        return args.file.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError as exc:
        raise ValueError(f"로그 파일을 읽을 수 없습니다: {args.file} ({exc})") from exc


def main(argv: list[str] | None = None) -> int:
    configure_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        lines = read_input(args)
    except ValueError as exc:
        parser.error(str(exc))
    operations = parse_operations(lines)
    filtered = filter_operations(
        operations,
        operation_type=args.operation,
        command_id=args.command_id,
        patrol_id=args.patrol_id,
    )
    if not filtered:
        print("ERROR: 조건에 맞는 Mapping·Patrol 명령을 찾지 못했습니다.", file=sys.stderr)
        return 1
    if args.json:
        render_json(filtered, sys.stdout)
    else:
        render_text(filtered, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
