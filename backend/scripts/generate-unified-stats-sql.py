"""Generate stats-dummy-unified.sql aligned with frontend MOCK_INSIGHT_* constants."""
import random
from pathlib import Path

TOTAL = 83
HANDLED = 59
ILLEGAL = 24
TRASH_TYPES = ["TRASH_DETECTED"] * 14 + ["RECYCLING_AREA_FULL"] * 4
OTHER_TYPES = ["UNREGISTERED_VEHICLE", "EMERGENCY"]
ZONES = [
    (10.0, 10.0, 35),
    (40.0, 10.0, 22),
    (10.0, 40.0, 14),
    (70.0, 10.0, 12),
]
TITLES = {
    "ILLEGAL_PARKING": "불법주차 감지",
    "TRASH_DETECTED": "쓰레기 적치 감지",
    "RECYCLING_AREA_FULL": "분리수거함 만재",
    "UNREGISTERED_VEHICLE": "미등록 차량 감지",
    "EMERGENCY": "응급상황 감지",
}


def build_month(year: int, month: int, day_count: int, seed: int):
    random.seed(seed)
    types = ["ILLEGAL_PARKING"] * ILLEGAL + TRASH_TYPES.copy()
    while len(types) < TOTAL:
        types.append(random.choice(OTHER_TYPES))
    types = types[:TOTAL]
    random.shuffle(types)

    statuses = ["COMPLETED"] * HANDLED + ["DETECTED"] * 12 + ["PROCESSING"] * 12
    assert len(statuses) == TOTAL
    random.shuffle(statuses)

    illegal_idxs = [i for i, t in enumerate(types) if t == "ILLEGAL_PARKING"]
    for idx in illegal_idxs[:3]:
        statuses[idx] = "DETECTED"

    zone_slots = []
    for x, y, cnt in ZONES:
        zone_slots += [(x, y)] * cnt
    random.shuffle(zone_slots)

    events = []
    for i in range(TOTAL):
        x, y = zone_slots[i]
        event_type = types[i]
        status = statuses[i]
        day = 1 + (i * day_count // TOTAL)
        hour = 6 + (i % 16)
        occurred = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:30:00"
        processed = "NULL"
        if status == "COMPLETED":
            processed = f"'{year:04d}-{month:02d}-{day:02d} {hour + 1:02d}:00:00'"
        title = TITLES.get(event_type, "이상 상황 감지")
        risk = "EMERGENCY" if event_type == "EMERGENCY" else "NORMAL"
        patrol_id = 1 + (i % 5)
        events.append(
            (
                patrol_id,
                2,
                event_type,
                title,
                occurred,
                x,
                y,
                risk,
                status,
                processed,
            )
        )
    return events


def main():
    lines = [
        "-- LLM 인사이트 목업(83건/월)과 통계 대시보드 실연동용 통합 더미",
        "-- 대상: robot_id=2 (apartment_complex_id=1)",
        "SET NAMES utf8mb4;",
        "DELETE FROM detected_events WHERE robot_id = 2;",
        "DELETE FROM analytics_ai_insights WHERE apartment_complex_id = 1;",
        "UPDATE checkpoints SET checkpoint_name='지하주차장 B2' WHERE checkpoint_id=1;",
        "UPDATE checkpoints SET checkpoint_name='101동' WHERE checkpoint_id=2;",
        "UPDATE checkpoints SET checkpoint_name='103동 화단' WHERE checkpoint_id=3;",
        (
            "INSERT INTO checkpoints (map_id, checkpoint_type, checkpoint_name, min_x, min_y, max_x, max_y) "
            "SELECT 2, 'START', '102동', 60.000, 0.000, 80.000, 20.000 FROM DUAL "
            "WHERE NOT EXISTS (SELECT 1 FROM checkpoints WHERE checkpoint_name='102동' AND map_id=2);"
        ),
        "UPDATE checkpoints SET checkpoint_type='START' WHERE checkpoint_name='102동' AND map_id=2;",
        "",
        "INSERT INTO detected_events (patrol_id, robot_id, event_type, event_title, occurred_at, x_coordinate, y_coordinate, risk_level, processing_status, processed_at) VALUES",
    ]

    all_events = build_month(2026, 6, 30, 42) + build_month(2026, 7, 31, 43)
    values = []
    for row in all_events:
        pid, rid, et, title, occ, x, y, risk, st, proc = row
        values.append(
            f"({pid}, {rid}, '{et}', '{title}', '{occ}', {x}, {y}, '{risk}', '{st}', {proc})"
        )
    lines.append(",\n".join(values) + ";")

    out = Path(__file__).with_name("stats-dummy-unified.sql")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(all_events)} events)")


if __name__ == "__main__":
    main()
