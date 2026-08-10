-- =============================================================================
-- 통계 연동 검증용 더미 (로컬 전용, Flyway 아님)
-- 대상: username=kimgm1018 → apartment_complex_id=1
-- 기간: 2026-07-01 ~ 2026-07-29 (증감 비교용으로 6월 일부 포함)
-- 표시: event_title / robot_name 에 [STATS_DUMMY] 포함 → 삭제 시 검색 가능
-- =============================================================================

START TRANSACTION;

SET @complex_id = (
  SELECT apartment_complex_id FROM members WHERE username = 'kimgm1018' LIMIT 1
);

-- 이미 넣은 더미가 있으면 로봇부터 연쇄 정리 (재실행 가능)
DELETE FROM patrol_checkpoint_visits
WHERE patrol_id IN (
  SELECT patrol_id FROM patrols WHERE robot_id IN (
    SELECT robot_id FROM patrol_robots
    WHERE apartment_complex_id = @complex_id AND robot_name LIKE '%[STATS_DUMMY]%'
  )
);
DELETE FROM detected_events
WHERE robot_id IN (
  SELECT robot_id FROM patrol_robots
  WHERE apartment_complex_id = @complex_id AND robot_name LIKE '%[STATS_DUMMY]%'
);
DELETE FROM patrols
WHERE robot_id IN (
  SELECT robot_id FROM patrol_robots
  WHERE apartment_complex_id = @complex_id AND robot_name LIKE '%[STATS_DUMMY]%'
);
DELETE FROM checkpoints
WHERE map_id IN (
  SELECT map_id FROM patrol_maps
  WHERE apartment_complex_id = @complex_id AND map_name LIKE '%[STATS_DUMMY]%'
);
DELETE FROM patrol_maps
WHERE apartment_complex_id = @complex_id AND map_name LIKE '%[STATS_DUMMY]%';
DELETE FROM patrol_robots
WHERE apartment_complex_id = @complex_id AND robot_name LIKE '%[STATS_DUMMY]%';

-- 1) 로봇
INSERT INTO patrol_robots (
  apartment_complex_id, robot_name, robot_serial_number, robot_status,
  battery_level, x_coordinate, y_coordinate, created_at, updated_at
) VALUES (
  @complex_id, 'R-01 [STATS_DUMMY]', 'STATS-DUMMY-R01', 'IDLE',
  88.00, 10.000, 10.000, NOW(6), NOW(6)
);
SET @robot_id = LAST_INSERT_ID();

-- 2) 지도 (파일 없어도 통계 구역 매핑용으로 URL 자리만)
INSERT INTO patrol_maps (
  apartment_complex_id, map_name, map_url, resolution,
  origin_x, origin_y, width, height, map_version, created_at, updated_at
) VALUES (
  @complex_id, '단지 지도 [STATS_DUMMY]', 'file:///stats-dummy-map.png', 0.0500,
  0.000, 0.000, 100, 100, 1, NOW(6), NOW(6)
);
SET @map_id = LAST_INSERT_ID();

-- 3) 구역 3개 (좌표 bbox — 이벤트 x,y가 이 안에 들어가야 파이차트에 잡힘)
INSERT INTO checkpoints (
  map_id, checkpoint_type, checkpoint_name, min_x, min_y, max_x, max_y, created_at, updated_at
) VALUES
  (@map_id, 'PARKING',        '지하주차장 B2', 0.000,  0.000,  20.000, 20.000, NOW(6), NOW(6)),
  (@map_id, 'START',          '101동',         30.000, 0.000,  50.000, 20.000, NOW(6), NOW(6)),
  (@map_id, 'RECYCLING_AREA', '분리수거장',     0.000,  30.000, 20.000, 50.000, NOW(6), NOW(6));
SET @cp_parking = LAST_INSERT_ID();
SET @cp_101 = @cp_parking + 1;
SET @cp_recycle = @cp_parking + 2;

-- 구역 중심 좌표 (이벤트 배치용)
SET @x_park = 10.000; SET @y_park = 10.000;
SET @x_101  = 40.000; SET @y_101  = 10.000;
SET @x_rec  = 10.000; SET @y_rec  = 40.000;

-- 4) 완료 순찰 — 6월 5건 + 7월 8건 = KPI/증감용
INSERT INTO patrols (
  robot_id, patrol_status, patrol_started_at, patrol_ended_at,
  total_duration, detected_event_count, start_battery_level, end_battery_level,
  created_at, updated_at
) VALUES
  (@robot_id, 'COMPLETED', '2026-06-05 09:00:00', '2026-06-05 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-06-12 09:00:00', '2026-06-12 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-06-18 09:00:00', '2026-06-18 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-06-22 09:00:00', '2026-06-22 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-06-28 09:00:00', '2026-06-28 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-07-02 09:00:00', '2026-07-02 10:30:00', 5400, 0, 92, 78, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-07-05 14:00:00', '2026-07-05 15:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-07-08 09:00:00', '2026-07-08 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-07-11 09:00:00', '2026-07-11 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-07-15 09:00:00', '2026-07-15 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-07-19 09:00:00', '2026-07-19 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-07-23 09:00:00', '2026-07-23 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6)),
  (@robot_id, 'COMPLETED', '2026-07-27 09:00:00', '2026-07-27 10:00:00', 3600, 0, 90, 80, NOW(6), NOW(6));

SET @patrol_first = LAST_INSERT_ID();
-- 위 INSERT 13건 → 마지막이 first+12. 7월 첫 순찰 = first+5
SET @p_jul1 = @patrol_first + 5;

-- 방문 (구역별 patrolCount용) — 7월 순찰 일부
INSERT INTO patrol_checkpoint_visits (patrol_id, checkpoint_id, visit_sequence, visited_at) VALUES
  (@p_jul1,     @cp_parking, 1, '2026-07-02 09:20:00'),
  (@p_jul1,     @cp_101,     2, '2026-07-02 09:40:00'),
  (@p_jul1 + 1, @cp_parking, 1, '2026-07-05 14:20:00'),
  (@p_jul1 + 1, @cp_recycle, 2, '2026-07-05 14:40:00'),
  (@p_jul1 + 2, @cp_parking, 1, '2026-07-08 09:15:00'),
  (@p_jul1 + 3, @cp_101,     1, '2026-07-11 09:20:00'),
  (@p_jul1 + 4, @cp_parking, 1, '2026-07-15 09:10:00'),
  (@p_jul1 + 4, @cp_recycle, 2, '2026-07-15 09:35:00'),
  (@p_jul1 + 5, @cp_parking, 1, '2026-07-19 09:20:00'),
  (@p_jul1 + 6, @cp_101,     1, '2026-07-23 09:25:00'),
  (@p_jul1 + 7, @cp_recycle, 1, '2026-07-27 09:30:00');

-- 5) 이벤트
-- 기대(대략, 이번 달 필터 month=7/1~7/31):
--   순찰 COMPLETED 8
--   이벤트 ~40 (7월) + 6월 소수
--   처리 COMPLETED / pending 섞음
--   시간대 8칸에 분산, 구역 3곳에 분산

INSERT INTO detected_events (
  patrol_id, robot_id, event_type, event_title, event_details, confidence,
  occurred_at, x_coordinate, y_coordinate, risk_level, processing_status, processed_at,
  created_at, updated_at
) VALUES
-- ----- 6월 (증감 previous) -----
(@patrol_first, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 6월 주차1', NULL, 0.900,
 '2026-06-10 10:00:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-06-10 10:15:00', NOW(6), NOW(6)),
(@patrol_first, @robot_id, 'TRASH_DETECTED', '[STATS_DUMMY] 6월 쓰레기1', NULL, 0.850,
 '2026-06-15 16:00:00', @x_rec, @y_rec, 'LOW', 'COMPLETED', '2026-06-15 16:20:00', NOW(6), NOW(6)),
(@patrol_first + 1, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 6월 주차2', NULL, 0.880,
 '2026-06-20 11:00:00', @x_park, @y_park, 'NORMAL', 'DETECTED', NULL, NOW(6), NOW(6)),
(@patrol_first + 2, @robot_id, 'EMERGENCY', '[STATS_DUMMY] 6월 긴급', NULL, 0.950,
 '2026-06-25 13:00:00', @x_101, @y_101, 'EMERGENCY', 'COMPLETED', '2026-06-25 13:30:00', NOW(6), NOW(6)),

-- ----- 7월: 일자·시간대·유형·상태·구역 분산 -----
-- 7/1 주차 주차장 COMPLETED 12분
(@p_jul1, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/1', NULL, 0.910,
 '2026-07-01 01:10:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-01 01:22:00', NOW(6), NOW(6)),
-- 7/2 쓰레기 분리수거 DETECTED (0-3시 슬롯)
(@p_jul1, @robot_id, 'TRASH_DETECTED', '[STATS_DUMMY] 쓰레기 7/2 새벽', NULL, 0.870,
 '2026-07-02 02:30:00', @x_rec, @y_rec, 'LOW', 'DETECTED', NULL, NOW(6), NOW(6)),
-- 7/3 미등록 주차장 PROCESSING
(@p_jul1, @robot_id, 'UNREGISTERED_VEHICLE', '[STATS_DUMMY] 미등록 7/3', NULL, 0.800,
 '2026-07-03 04:20:00', @x_park, @y_park, 'NORMAL', 'PROCESSING', NULL, NOW(6), NOW(6)),
-- 7/4 분리수거 포화 7시
(@p_jul1 + 1, @robot_id, 'RECYCLING_AREA_FULL', '[STATS_DUMMY] 포화 7/4', NULL, 0.860,
 '2026-07-04 07:15:00', @x_rec, @y_rec, 'NORMAL', 'COMPLETED', '2026-07-04 07:28:00', NOW(6), NOW(6)),
-- 7/5 주차 101동 10시
(@p_jul1 + 1, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/5 101', NULL, 0.920,
 '2026-07-05 10:40:00', @x_101, @y_101, 'NORMAL', 'COMPLETED', '2026-07-05 10:55:00', NOW(6), NOW(6)),
-- 7/6 쓰레기 12시
(@p_jul1 + 1, @robot_id, 'TRASH_DETECTED', '[STATS_DUMMY] 쓰레기 7/6', NULL, 0.840,
 '2026-07-06 12:10:00', @x_rec, @y_rec, 'LOW', 'COMPLETED', '2026-07-06 12:20:00', NOW(6), NOW(6)),
-- 7/7 긴급 14시 주차장
(@p_jul1 + 2, @robot_id, 'EMERGENCY', '[STATS_DUMMY] 긴급 7/7', NULL, 0.970,
 '2026-07-07 14:05:00', @x_park, @y_park, 'EMERGENCY', 'PROCESSING', NULL, NOW(6), NOW(6)),
-- 7/8 주차 16시
(@p_jul1 + 2, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/8', NULL, 0.900,
 '2026-07-08 16:30:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-08 16:42:00', NOW(6), NOW(6)),
-- 7/9 쓰레기 19시
(@p_jul1 + 2, @robot_id, 'TRASH_DETECTED', '[STATS_DUMMY] 쓰레기 7/9', NULL, 0.830,
 '2026-07-09 19:20:00', @x_rec, @y_rec, 'LOW', 'DETECTED', NULL, NOW(6), NOW(6)),
-- 7/10 미등록 22시
(@p_jul1 + 3, @robot_id, 'UNREGISTERED_VEHICLE', '[STATS_DUMMY] 미등록 7/10', NULL, 0.810,
 '2026-07-10 22:10:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-10 22:25:00', NOW(6), NOW(6)),
-- 7/11~ 추가 다수 (추이·파이 채우기)
(@p_jul1 + 3, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/11', NULL, 0.900,
 '2026-07-11 09:00:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-11 09:12:00', NOW(6), NOW(6)),
(@p_jul1 + 3, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/11b', NULL, 0.890,
 '2026-07-11 15:30:00', @x_park, @y_park, 'NORMAL', 'DETECTED', NULL, NOW(6), NOW(6)),
(@p_jul1 + 4, @robot_id, 'TRASH_DETECTED', '[STATS_DUMMY] 쓰레기 7/12', NULL, 0.850,
 '2026-07-12 08:00:00', @x_rec, @y_rec, 'LOW', 'COMPLETED', '2026-07-12 08:18:00', NOW(6), NOW(6)),
(@p_jul1 + 4, @robot_id, 'RECYCLING_AREA_FULL', '[STATS_DUMMY] 포화 7/13', NULL, 0.870,
 '2026-07-13 11:00:00', @x_rec, @y_rec, 'NORMAL', 'COMPLETED', '2026-07-13 11:10:00', NOW(6), NOW(6)),
(@p_jul1 + 4, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/14', NULL, 0.910,
 '2026-07-14 13:20:00', @x_101, @y_101, 'NORMAL', 'COMPLETED', '2026-07-14 13:35:00', NOW(6), NOW(6)),
(@p_jul1 + 4, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/15', NULL, 0.920,
 '2026-07-15 17:00:00', @x_park, @y_park, 'NORMAL', 'PROCESSING', NULL, NOW(6), NOW(6)),
(@p_jul1 + 5, @robot_id, 'TRASH_DETECTED', '[STATS_DUMMY] 쓰레기 7/16', NULL, 0.840,
 '2026-07-16 03:00:00', @x_rec, @y_rec, 'LOW', 'DETECTED', NULL, NOW(6), NOW(6)),
(@p_jul1 + 5, @robot_id, 'EMERGENCY', '[STATS_DUMMY] 긴급 7/17', NULL, 0.960,
 '2026-07-17 20:00:00', @x_101, @y_101, 'EMERGENCY', 'COMPLETED', '2026-07-17 20:25:00', NOW(6), NOW(6)),
(@p_jul1 + 5, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/18', NULL, 0.900,
 '2026-07-18 10:00:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-18 10:11:00', NOW(6), NOW(6)),
(@p_jul1 + 5, @robot_id, 'UNREGISTERED_VEHICLE', '[STATS_DUMMY] 미등록 7/19', NULL, 0.820,
 '2026-07-19 14:40:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-19 14:55:00', NOW(6), NOW(6)),
(@p_jul1 + 6, @robot_id, 'TRASH_DETECTED', '[STATS_DUMMY] 쓰레기 7/20', NULL, 0.850,
 '2026-07-20 06:30:00', @x_rec, @y_rec, 'LOW', 'COMPLETED', '2026-07-20 06:40:00', NOW(6), NOW(6)),
(@p_jul1 + 6, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/21', NULL, 0.900,
 '2026-07-21 18:10:00', @x_101, @y_101, 'NORMAL', 'DETECTED', NULL, NOW(6), NOW(6)),
(@p_jul1 + 6, @robot_id, 'RECYCLING_AREA_FULL', '[STATS_DUMMY] 포화 7/22', NULL, 0.880,
 '2026-07-22 21:00:00', @x_rec, @y_rec, 'NORMAL', 'PROCESSING', NULL, NOW(6), NOW(6)),
(@p_jul1 + 6, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/23', NULL, 0.910,
 '2026-07-23 09:30:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-23 09:45:00', NOW(6), NOW(6)),
(@p_jul1 + 7, @robot_id, 'TRASH_DETECTED', '[STATS_DUMMY] 쓰레기 7/24', NULL, 0.860,
 '2026-07-24 12:00:00', @x_rec, @y_rec, 'LOW', 'COMPLETED', '2026-07-24 12:08:00', NOW(6), NOW(6)),
(@p_jul1 + 7, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/25', NULL, 0.900,
 '2026-07-25 15:00:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-25 15:20:00', NOW(6), NOW(6)),
(@p_jul1 + 7, @robot_id, 'EMERGENCY', '[STATS_DUMMY] 긴급 7/26', NULL, 0.980,
 '2026-07-26 08:00:00', @x_101, @y_101, 'EMERGENCY', 'DETECTED', NULL, NOW(6), NOW(6)),
(@p_jul1 + 7, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/27', NULL, 0.900,
 '2026-07-27 11:00:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-27 11:14:00', NOW(6), NOW(6)),
(@p_jul1 + 7, @robot_id, 'TRASH_DETECTED', '[STATS_DUMMY] 쓰레기 7/28', NULL, 0.850,
 '2026-07-28 16:00:00', @x_rec, @y_rec, 'LOW', 'COMPLETED', '2026-07-28 16:12:00', NOW(6), NOW(6)),
(@p_jul1 + 7, @robot_id, 'UNREGISTERED_VEHICLE', '[STATS_DUMMY] 미등록 7/29', NULL, 0.830,
 '2026-07-29 10:00:00', @x_park, @y_park, 'NORMAL', 'PROCESSING', NULL, NOW(6), NOW(6)),
-- 주차장 비중을 높여 파이차트 차이 보이게
(@p_jul1 + 7, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/29b', NULL, 0.900,
 '2026-07-29 13:00:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-29 13:10:00', NOW(6), NOW(6)),
(@p_jul1 + 7, @robot_id, 'ILLEGAL_PARKING', '[STATS_DUMMY] 주차 7/29c', NULL, 0.900,
 '2026-07-29 19:00:00', @x_park, @y_park, 'NORMAL', 'COMPLETED', '2026-07-29 19:09:00', NOW(6), NOW(6));

COMMIT;

-- 검증 요약
SELECT 'robots' AS kind, COUNT(*) AS cnt FROM patrol_robots WHERE robot_name LIKE '%[STATS_DUMMY]%'
UNION ALL
SELECT 'patrols_jul_completed', COUNT(*) FROM patrols p
  JOIN patrol_robots r ON r.robot_id = p.robot_id
  WHERE r.robot_name LIKE '%[STATS_DUMMY]%' AND p.patrol_status='COMPLETED'
    AND p.patrol_started_at >= '2026-07-01' AND p.patrol_started_at < '2026-08-01'
UNION ALL
SELECT 'events_jul', COUNT(*) FROM detected_events e
  JOIN patrol_robots r ON r.robot_id = e.robot_id
  WHERE r.robot_name LIKE '%[STATS_DUMMY]%'
    AND e.occurred_at >= '2026-07-01' AND e.occurred_at < '2026-08-01'
UNION ALL
SELECT 'checkpoints', COUNT(*) FROM checkpoints c
  JOIN patrol_maps m ON m.map_id = c.map_id
  WHERE m.map_name LIKE '%[STATS_DUMMY]%';
