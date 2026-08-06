-- OneLoop 로컬 운영 화면 데이터 구성 스크립트 (MySQL 8.4 / Flyway V16 기준)
-- 비어 있는 로컬 DB에서도 실행할 수 있도록 단지와 로그인 관리자를 함께 구성합니다.
-- 생성 계정: ssafy1234 / password123!
-- 해당 회원의 단지에 로봇, 순찰, 이벤트, 처리 이력, 알림 및 통계 데이터를 구성합니다.
-- 단지에 지도가 있으면 기존 지도 1개를 사용하고, 없을 때만 지도를 1개 생성합니다.

SET NAMES utf8mb4;
SET time_zone = '+09:00';
START TRANSACTION;

SET @login_username = 'ssafy1234';
SET @login_password_hash = '$2a$10$VDWhzkw.m0A2nbecXjbi8umu.XHLpejPtqGUALVuXHI6sk7Srk2cu';

INSERT INTO apartment_complexes (apartment_name,address,postal_code,created_at,updated_at)
SELECT '한빛 센트럴파크','서울특별시 송파구 한빛로 127','05542',NOW(6),NOW(6)
WHERE NOT EXISTS (
    SELECT 1 FROM apartment_complexes
    WHERE apartment_name='한빛 센트럴파크' AND address='서울특별시 송파구 한빛로 127'
);

SET @complex_id = (
    SELECT apartment_complex_id FROM apartment_complexes
    WHERE apartment_name='한빛 센트럴파크' AND address='서울특별시 송파구 한빛로 127'
    ORDER BY apartment_complex_id LIMIT 1
);

INSERT INTO members (
    apartment_complex_id,username,password,name,phone_number,member_status,created_at,updated_at
)
VALUES (
    @complex_id,@login_username,@login_password_hash,'김도현 경비원','010-2936-7401','ACTIVE',NOW(6),NOW(6)
)
ON DUPLICATE KEY UPDATE apartment_complex_id=VALUES(apartment_complex_id),password=VALUES(password),
                        name=VALUES(name),phone_number=VALUES(phone_number),member_status='ACTIVE',updated_at=NOW(6);

DELETE FROM members
WHERE username='local_security_admin' AND apartment_complex_id=@complex_id;

SELECT @complex_id AS local_apartment_complex_id, @login_username AS login_username;

-- -----------------------------------------------------------------------------
-- 재실행 정리: 이 스크립트가 관리하는 로봇 일련번호만 정확히 대상으로 삼는다.
-- -----------------------------------------------------------------------------
DELETE n FROM notifications n
JOIN detected_events e ON e.event_id = n.event_id
JOIN patrol_robots r ON r.robot_id = e.robot_id
WHERE r.apartment_complex_id = @complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

DELETE h FROM event_processing_history h
JOIN detected_events e ON e.event_id = h.event_id
JOIN patrol_robots r ON r.robot_id = e.robot_id
WHERE r.apartment_complex_id = @complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

DELETE ee FROM event_evidence ee
JOIN detected_events e ON e.event_id = ee.event_id
JOIN patrol_robots r ON r.robot_id = e.robot_id
WHERE r.apartment_complex_id = @complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

DELETE s FROM patrol_ai_summaries s
JOIN patrols p ON p.patrol_id = s.patrol_id
JOIN patrol_robots r ON r.robot_id = p.robot_id
WHERE r.apartment_complex_id = @complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

DELETE v FROM patrol_checkpoint_visits v
JOIN patrols p ON p.patrol_id = v.patrol_id
JOIN patrol_robots r ON r.robot_id = p.robot_id
WHERE r.apartment_complex_id = @complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

DELETE rp FROM route_positions rp
JOIN patrols p ON p.patrol_id = rp.patrol_id
JOIN patrol_robots r ON r.robot_id = p.robot_id
WHERE r.apartment_complex_id = @complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

DELETE e FROM detected_events e
JOIN patrol_robots r ON r.robot_id = e.robot_id
WHERE r.apartment_complex_id = @complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

DELETE p FROM patrols p
JOIN patrol_robots r ON r.robot_id = p.robot_id
WHERE r.apartment_complex_id = @complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

DELETE ms FROM mapping_sessions ms
JOIN patrol_robots r ON r.robot_id = ms.robot_id
WHERE r.apartment_complex_id = @complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

DELETE FROM patrol_robots
WHERE apartment_complex_id = @complex_id
  AND robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

-- -----------------------------------------------------------------------------
-- 같은 단지 경비 회원 4명을 이벤트 처리 이력 담당자로 사용한다.
-- 입주민은 알림 수신 기록과 등록 차량 조회를 위해 별도 구성한다.
-- -----------------------------------------------------------------------------
DELETE FROM members
WHERE apartment_complex_id=@complex_id
  AND username LIKE 'guard\_%';

SET @guard_1 = (SELECT member_id FROM members
                WHERE apartment_complex_id=@complex_id AND username='ssafy1234' LIMIT 1);

INSERT INTO members (
    apartment_complex_id,username,password,name,phone_number,member_status,created_at,updated_at
)
VALUES
(@complex_id,CONCAT('guard_park_seongho_',@complex_id),@login_password_hash,'박성호 경비원','010-7412-3058','ACTIVE',NOW(6),NOW(6)),
(@complex_id,CONCAT('guard_lee_jaehyun_',@complex_id),@login_password_hash,'이재현 경비원','010-5286-1943','ACTIVE',NOW(6),NOW(6)),
(@complex_id,CONCAT('guard_choi_minsu_',@complex_id),@login_password_hash,'최민수 경비원','010-9364-5270','ACTIVE',NOW(6),NOW(6));
SET @guard_2 = LAST_INSERT_ID();
SET @guard_3 = @guard_2 + 1;
SET @guard_4 = @guard_2 + 2;

INSERT INTO residents (apartment_complex_id, name, phone_number, building_number,
                       unit_number, notification_enabled, created_at, updated_at)
VALUES
(@complex_id, '김민준', '010-3214-8821', '101', '1203', TRUE, NOW(6), NOW(6)),
(@complex_id, '최서윤', '010-4728-1156', '102', '804',  TRUE, NOW(6), NOW(6)),
(@complex_id, '정우진', '010-5861-7342', '103', '1502', TRUE, NOW(6), NOW(6))
ON DUPLICATE KEY UPDATE name = VALUES(name), notification_enabled = TRUE, updated_at = NOW(6);

SET @resident_1 = (SELECT resident_id FROM residents WHERE apartment_complex_id=@complex_id AND phone_number='010-3214-8821' LIMIT 1);
SET @resident_2 = (SELECT resident_id FROM residents WHERE apartment_complex_id=@complex_id AND phone_number='010-4728-1156' LIMIT 1);
SET @resident_3 = (SELECT resident_id FROM residents WHERE apartment_complex_id=@complex_id AND phone_number='010-5861-7342' LIMIT 1);

INSERT INTO registered_vehicles (resident_id, license_plate, disabled_vehicle, created_at, updated_at)
VALUES
(@resident_1, '12가 4831', FALSE, NOW(6), NOW(6)),
(@resident_2, '38나 7216', FALSE, NOW(6), NOW(6)),
(@resident_3, '61모 2059', TRUE,  NOW(6), NOW(6))
ON DUPLICATE KEY UPDATE resident_id=VALUES(resident_id), disabled_vehicle=VALUES(disabled_vehicle), updated_at=NOW(6);

-- -----------------------------------------------------------------------------
-- 단지 지도: 기존 지도가 있으면 추가하지 않는다(단지당 정확히 1개).
-- -----------------------------------------------------------------------------
INSERT INTO patrol_maps (
    apartment_complex_id, map_name, map_url, resolution, origin_x, origin_y,
    origin_yaw, width, height, map_version, created_at, updated_at
)
SELECT @complex_id, '단지 통합 순찰 지도', '/api/map/files/24037a9d-f788-4a82-9bfe-744c900bc494.png',
       0.1250, 0.000, 0.000, 0.00, 766, 626, 1, NOW(6), NOW(6)
WHERE @complex_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM patrol_maps WHERE apartment_complex_id=@complex_id);

UPDATE patrol_maps
SET map_url='/api/map/files/24037a9d-f788-4a82-9bfe-744c900bc494.png',
    resolution=0.1250, origin_x=0.000, origin_y=0.000, origin_yaw=0.00,
    width=766, height=626, updated_at=NOW(6)
WHERE apartment_complex_id=@complex_id AND map_name='단지 통합 순찰 지도';

SET @map_id = (SELECT map_id FROM patrol_maps WHERE apartment_complex_id=@complex_id LIMIT 1);
SET @map_version = (SELECT COALESCE(map_version, 1) FROM patrol_maps WHERE map_id=@map_id);

DELETE FROM checkpoints WHERE map_id=@map_id;

INSERT INTO checkpoints (map_id, checkpoint_type, checkpoint_name, min_x, min_y, max_x, max_y,
                         active, created_at, updated_at)
VALUES
(@map_id,'START',          '정문 경비초소',       4.000,  4.000, 12.000, 12.000, TRUE, NOW(6), NOW(6)),
(@map_id,'PARKING',        '주차장 A',           18.000, 12.000, 36.000, 27.000, TRUE, NOW(6), NOW(6)),
(@map_id,'PARKING',        '주차장 B',           40.000, 12.000, 58.000, 27.000, TRUE, NOW(6), NOW(6)),
(@map_id,'PARKING',        '주차장 C',           28.000, 38.000, 46.000, 55.000, TRUE, NOW(6), NOW(6)),
(@map_id,'RECYCLING_AREA', '재활용 분리수거장',  63.000, 15.000, 76.000, 29.000, TRUE, NOW(6), NOW(6)),
(@map_id,'DANGER_ZONE',    '후문 진입로',        68.000, 47.000, 80.000, 61.000, TRUE, NOW(6), NOW(6)),
(@map_id,'DESTINATION',    '순찰 복귀 지점',      7.000,  7.000, 11.000, 11.000, TRUE, NOW(6), NOW(6));

SET @cp_start = (SELECT checkpoint_id FROM checkpoints WHERE map_id=@map_id AND checkpoint_name='정문 경비초소');
SET @cp_parking_a = (SELECT checkpoint_id FROM checkpoints WHERE map_id=@map_id AND checkpoint_name='주차장 A');
SET @cp_parking_b = (SELECT checkpoint_id FROM checkpoints WHERE map_id=@map_id AND checkpoint_name='주차장 B');
SET @cp_parking_c = (SELECT checkpoint_id FROM checkpoints WHERE map_id=@map_id AND checkpoint_name='주차장 C');
SET @cp_recycle = (SELECT checkpoint_id FROM checkpoints WHERE map_id=@map_id AND checkpoint_name='재활용 분리수거장');
SET @cp_gate = (SELECT checkpoint_id FROM checkpoints WHERE map_id=@map_id AND checkpoint_name='후문 진입로');

-- -----------------------------------------------------------------------------
-- 로봇: 이름과 일련번호 모두 RO-Ki 접두어를 사용한다.
-- -----------------------------------------------------------------------------
INSERT INTO patrol_robots (
 apartment_complex_id, robot_name, robot_serial_number, service_token,
 x_coordinate, y_coordinate, heading, location_updated_at, robot_status,
 obstacle_direction, obstacle_message, battery_level, camera_status, lidar_status,
 motor_status, line_sensor_status, status_reported_at, last_connected_at, created_at, updated_at
)
VALUES
(@complex_id,'RO-Ki3214','RO-Ki3214',NULL,  9.200,  8.400,  12.50,NOW(6),'IDLE',NULL,NULL,87.00,'NORMAL','NORMAL','NORMAL','NORMAL',NOW(6),NOW(6),'2026-04-08 09:20:00',NOW(6)),
(@complex_id,'RO-Ki4728','RO-Ki4728',NULL, 31.500, 21.200,  91.20,NOW(6),'PATROLLING',NULL,NULL,73.00,'NORMAL','NORMAL','NORMAL','NORMAL',NOW(6),NOW(6),'2026-04-19 14:10:00',NOW(6)),
(@complex_id,'RO-Ki5861','RO-Ki5861',NULL, 10.100,  9.000, 182.00,NOW(6),'CHARGING',NULL,NULL,42.00,'NORMAL','NORMAL','NORMAL','NORMAL',NOW(6),NOW(6),'2026-05-02 11:30:00',NOW(6)),
(@complex_id,'RO-Ki7395','RO-Ki7395',NULL, 72.400, 53.600, 267.40,NOW(6),'OBSTACLE_STOP','FRONT','전방 0.4m 장애물 감지',64.00,'NORMAL','NORMAL','NORMAL','NORMAL',NOW(6),NOW(6),'2026-05-17 16:45:00',NOW(6)),
(@complex_id,'RO-Ki8042','RO-Ki8042',NULL, 48.300, 20.500, 136.80,DATE_SUB(NOW(6),INTERVAL 2 HOUR),'OFFLINE',NULL,NULL,19.00,'NEEDS_INSPECTION','DISCONNECTED','NORMAL','NORMAL',DATE_SUB(NOW(6),INTERVAL 2 HOUR),DATE_SUB(NOW(6),INTERVAL 2 HOUR),'2026-06-01 10:05:00',NOW(6));

SET @r1=(SELECT robot_id FROM patrol_robots WHERE robot_serial_number='RO-Ki3214');
SET @r2=(SELECT robot_id FROM patrol_robots WHERE robot_serial_number='RO-Ki4728');
SET @r3=(SELECT robot_id FROM patrol_robots WHERE robot_serial_number='RO-Ki5861');
SET @r4=(SELECT robot_id FROM patrol_robots WHERE robot_serial_number='RO-Ki7395');
SET @r5=(SELECT robot_id FROM patrol_robots WHERE robot_serial_number='RO-Ki8042');

-- 완료 순찰 10건: 월간/주간/일간 통계와 로봇별 분포가 모두 보이도록 배치한다.
INSERT INTO patrols (robot_id,command_id,completion_requested,patrol_status,patrol_started_at,patrol_ended_at,
                     total_duration,detected_event_count,start_battery_level,end_battery_level,created_at,updated_at)
VALUES
(@r1,'4d4d5d70-1001-4000-8000-000000000001',FALSE,'COMPLETED','2026-07-08 06:00:00','2026-07-08 07:12:00',4320,2,96,81,'2026-07-08 06:00:00','2026-07-08 07:12:00'),
(@r2,'4d4d5d70-1002-4000-8000-000000000002',FALSE,'COMPLETED','2026-07-12 21:00:00','2026-07-12 22:05:00',3900,1,91,78,'2026-07-12 21:00:00','2026-07-12 22:05:00'),
(@r3,'4d4d5d70-1003-4000-8000-000000000003',FALSE,'COMPLETED','2026-07-18 14:00:00','2026-07-18 15:18:00',4680,2,89,72,'2026-07-18 14:00:00','2026-07-18 15:18:00'),
(@r1,'4d4d5d70-1004-4000-8000-000000000004',FALSE,'COMPLETED','2026-07-23 05:40:00','2026-07-23 06:55:00',4500,1,94,79,'2026-07-23 05:40:00','2026-07-23 06:55:00'),
(@r4,'4d4d5d70-1005-4000-8000-000000000005',FALSE,'COMPLETED','2026-07-29 22:10:00','2026-07-29 23:24:00',4440,2,88,70,'2026-07-29 22:10:00','2026-07-29 23:24:00'),
(@r2,'4d4d5d70-1006-4000-8000-000000000006',FALSE,'COMPLETED','2026-08-01 06:10:00','2026-08-01 07:28:00',4680,2,93,76,'2026-08-01 06:10:00','2026-08-01 07:28:00'),
(@r3,'4d4d5d70-1007-4000-8000-000000000007',FALSE,'COMPLETED','2026-08-02 13:30:00','2026-08-02 14:42:00',4320,1,86,71,'2026-08-02 13:30:00','2026-08-02 14:42:00'),
(@r1,'4d4d5d70-1008-4000-8000-000000000008',FALSE,'COMPLETED','2026-08-03 21:00:00','2026-08-03 22:21:00',4860,2,97,80,'2026-08-03 21:00:00','2026-08-03 22:21:00'),
(@r4,'4d4d5d70-1009-4000-8000-000000000009',FALSE,'COMPLETED','2026-08-04 05:50:00','2026-08-04 07:02:00',4320,1,84,69,'2026-08-04 05:50:00','2026-08-04 07:02:00'),
(@r2,'4d4d5d70-1010-4000-8000-000000000010',FALSE,'COMPLETED','2026-08-05 20:40:00','2026-08-05 21:58:00',4680,2,92,74,'2026-08-05 20:40:00','2026-08-05 21:58:00');
SET @p1=LAST_INSERT_ID();

-- 진행/중지/실패 상태도 순찰 관리 필터에서 확인할 수 있다.
INSERT INTO patrols (robot_id,command_id,completion_requested,patrol_status,patrol_started_at,patrol_ended_at,
                     total_duration,detected_event_count,start_battery_level,end_battery_level,created_at,updated_at)
VALUES
(@r2,'4d4d5d70-1011-4000-8000-000000000011',FALSE,'IN_PROGRESS','2026-08-06 14:10:00',NULL,NULL,1,82,NULL,'2026-08-06 14:10:00',NOW(6)),
(@r5,'4d4d5d70-1012-4000-8000-000000000012',FALSE,'STOPPED','2026-08-05 02:10:00','2026-08-05 02:44:00',2040,0,55,46,'2026-08-05 02:10:00','2026-08-05 02:44:00'),
(@r4,'4d4d5d70-1013-4000-8000-000000000013',FALSE,'FAILED','2026-08-04 23:10:00','2026-08-04 23:27:00',1020,1,71,66,'2026-08-04 23:10:00','2026-08-04 23:27:00');
SET @p_progress=LAST_INSERT_ID();

-- 경로 좌표 및 체크포인트 방문 기록
INSERT INTO route_positions (patrol_id,x_coordinate,y_coordinate,recorded_at,created_at,updated_at)
SELECT @p1+patrol_offset,x,y,
       DATE_ADD((SELECT patrol_started_at FROM patrols WHERE patrol_id=@p1+patrol_offset),
                INTERVAL minute_offset MINUTE),NOW(6),NOW(6)
FROM (
 -- 각 순찰의 체크포인트 순서와 일치하는 개별 개방형 경로. 출발점으로 되감는 선을 만들지 않는다.
 SELECT 0 patrol_offset,0 minute_offset,8.000 x,8.000 y
 UNION ALL SELECT 0,10,18.000,14.000 UNION ALL SELECT 0,20,27.000,19.500 UNION ALL SELECT 0,32,31.000,32.000 UNION ALL SELECT 0,43,37.000,46.500 UNION ALL SELECT 0,55,55.000,50.000 UNION ALL SELECT 0,65,74.000,54.000
 UNION ALL SELECT 1,0,8.000,8.000 UNION ALL SELECT 1,10,24.000,13.000 UNION ALL SELECT 1,20,49.000,19.500 UNION ALL SELECT 1,30,60.000,21.000 UNION ALL SELECT 1,40,69.500,22.000 UNION ALL SELECT 1,52,72.000,39.000 UNION ALL SELECT 1,62,74.000,54.000
 UNION ALL SELECT 2,0,8.000,8.000 UNION ALL SELECT 2,10,18.000,14.000 UNION ALL SELECT 2,18,27.000,19.500 UNION ALL SELECT 2,28,38.000,19.500 UNION ALL SELECT 2,36,49.000,19.500 UNION ALL SELECT 2,48,59.000,21.000 UNION ALL SELECT 2,60,69.500,22.000
 UNION ALL SELECT 3,0,8.000,8.000 UNION ALL SELECT 3,10,17.000,18.000 UNION ALL SELECT 3,20,27.000,32.000 UNION ALL SELECT 3,30,37.000,46.500 UNION ALL SELECT 3,40,49.000,49.000 UNION ALL SELECT 3,52,62.000,52.000 UNION ALL SELECT 3,62,74.000,54.000
 UNION ALL SELECT 4,0,8.000,8.000 UNION ALL SELECT 4,10,28.000,14.000 UNION ALL SELECT 4,20,49.000,19.500 UNION ALL SELECT 4,31,44.000,33.000 UNION ALL SELECT 4,41,37.000,46.500 UNION ALL SELECT 4,51,53.000,34.000 UNION ALL SELECT 4,62,69.500,22.000
 UNION ALL SELECT 5,0,8.000,8.000 UNION ALL SELECT 5,10,18.000,14.000 UNION ALL SELECT 5,20,27.000,19.500 UNION ALL SELECT 5,31,46.000,20.000 UNION ALL SELECT 5,41,69.500,22.000 UNION ALL SELECT 5,52,72.000,39.000 UNION ALL SELECT 5,62,74.000,54.000
 UNION ALL SELECT 6,0,8.000,8.000 UNION ALL SELECT 6,10,18.000,14.000 UNION ALL SELECT 6,20,27.000,19.500 UNION ALL SELECT 6,30,38.000,19.500 UNION ALL SELECT 6,40,49.000,19.500 UNION ALL SELECT 6,50,43.000,33.000 UNION ALL SELECT 6,62,37.000,46.500
 UNION ALL SELECT 7,0,8.000,8.000 UNION ALL SELECT 7,10,29.000,14.000 UNION ALL SELECT 7,20,50.000,18.000 UNION ALL SELECT 7,30,69.500,22.000 UNION ALL SELECT 7,40,54.000,34.000 UNION ALL SELECT 7,50,37.000,46.500 UNION ALL SELECT 7,62,74.000,54.000
 UNION ALL SELECT 8,0,8.000,8.000 UNION ALL SELECT 8,10,22.000,13.000 UNION ALL SELECT 8,22,36.000,17.000 UNION ALL SELECT 8,32,49.000,19.500 UNION ALL SELECT 8,42,58.000,31.000 UNION ALL SELECT 8,52,66.000,43.000 UNION ALL SELECT 8,62,74.000,54.000
 UNION ALL SELECT 9,0,8.000,8.000 UNION ALL SELECT 9,9,27.000,19.500 UNION ALL SELECT 9,18,49.000,19.500 UNION ALL SELECT 9,28,69.500,22.000 UNION ALL SELECT 9,39,53.000,34.000 UNION ALL SELECT 9,49,37.000,46.500 UNION ALL SELECT 9,60,74.000,54.000
) route_by_patrol;

INSERT INTO patrol_checkpoint_visits (patrol_id,checkpoint_id,visit_sequence,visited_at)
SELECT @p1+patrol_offset, checkpoint_id, visit_sequence,
       DATE_ADD((SELECT patrol_started_at FROM patrols WHERE patrol_id=@p1+patrol_offset),
                INTERVAL minute_offset MINUTE)
FROM (
 -- 1차: 정문 → 주차장 A → 주차장 C → 후문
 SELECT 0 patrol_offset,@cp_start checkpoint_id,1 visit_sequence,2 minute_offset
 UNION ALL SELECT 0,@cp_parking_a,2,15 UNION ALL SELECT 0,@cp_parking_c,3,38 UNION ALL SELECT 0,@cp_gate,4,56
 -- 2차: 정문 → 주차장 B → 분리수거장 → 후문
 UNION ALL SELECT 1,@cp_start,1,2 UNION ALL SELECT 1,@cp_parking_b,2,18 UNION ALL SELECT 1,@cp_recycle,3,37 UNION ALL SELECT 1,@cp_gate,4,55
 -- 3차: 정문 → 주차장 A → 주차장 B → 분리수거장
 UNION ALL SELECT 2,@cp_start,1,2 UNION ALL SELECT 2,@cp_parking_a,2,14 UNION ALL SELECT 2,@cp_parking_b,3,30 UNION ALL SELECT 2,@cp_recycle,4,50
 -- 4차: 정문 → 주차장 C → 후문
 UNION ALL SELECT 3,@cp_start,1,2 UNION ALL SELECT 3,@cp_parking_c,2,28 UNION ALL SELECT 3,@cp_gate,3,52
 -- 5차: 정문 → 주차장 B → 주차장 C → 분리수거장
 UNION ALL SELECT 4,@cp_start,1,2 UNION ALL SELECT 4,@cp_parking_b,2,16 UNION ALL SELECT 4,@cp_parking_c,3,36 UNION ALL SELECT 4,@cp_recycle,4,54
 -- 6차: 정문 → 주차장 A → 분리수거장 → 후문
 UNION ALL SELECT 5,@cp_start,1,2 UNION ALL SELECT 5,@cp_parking_a,2,15 UNION ALL SELECT 5,@cp_recycle,3,35 UNION ALL SELECT 5,@cp_gate,4,55
 -- 7차: 정문 → 주차장 A → 주차장 B → 주차장 C
 UNION ALL SELECT 6,@cp_start,1,2 UNION ALL SELECT 6,@cp_parking_a,2,14 UNION ALL SELECT 6,@cp_parking_b,3,29 UNION ALL SELECT 6,@cp_parking_c,4,50
 -- 8차: 정문 → 분리수거장 → 주차장 C → 후문
 UNION ALL SELECT 7,@cp_start,1,2 UNION ALL SELECT 7,@cp_recycle,2,20 UNION ALL SELECT 7,@cp_parking_c,3,39 UNION ALL SELECT 7,@cp_gate,4,57
 -- 9차: 정문 → 주차장 B → 후문
 UNION ALL SELECT 8,@cp_start,1,2 UNION ALL SELECT 8,@cp_parking_b,2,25 UNION ALL SELECT 8,@cp_gate,3,53
 -- 10차: 정문 → 주차장 A → 주차장 B → 분리수거장 → 주차장 C → 후문
 UNION ALL SELECT 9,@cp_start,1,2 UNION ALL SELECT 9,@cp_parking_a,2,12 UNION ALL SELECT 9,@cp_parking_b,3,24
 UNION ALL SELECT 9,@cp_recycle,4,36 UNION ALL SELECT 9,@cp_parking_c,5,47 UNION ALL SELECT 9,@cp_gate,6,58
) varied_routes;

-- 순찰 AI 요약: 완료/처리/대기/실패 상태를 모두 제공한다.
INSERT INTO patrol_ai_summaries (patrol_id,generation_status,summary_content,created_at,updated_at)
SELECT p.patrol_id,
       CASE MOD(p.patrol_id-@p1,4) WHEN 0 THEN 'COMPLETED' WHEN 1 THEN 'COMPLETED' WHEN 2 THEN 'PROCESSING' ELSE 'PENDING' END,
       CASE WHEN MOD(p.patrol_id-@p1,4) IN (0,1)
            THEN CONCAT('총 ',p.total_duration DIV 60,'분간 단지 주요 구역을 순찰했습니다. 경로 이탈 없이 지정 구역을 모두 확인했으며 감지 이벤트는 관제실 처리 절차에 따라 기록되었습니다.')
            ELSE NULL END,
       p.patrol_ended_at, p.patrol_ended_at
FROM patrols p
WHERE p.command_id BETWEEN '4d4d5d70-1001-4000-8000-000000000001' AND '4d4d5d70-1010-4000-8000-000000000010';

-- -----------------------------------------------------------------------------
-- 모든 이벤트 유형 5종 + 모든 위험도/처리 상태
-- -----------------------------------------------------------------------------
INSERT INTO detected_events (
 patrol_id,robot_id,event_type,event_title,event_details,confidence,occurred_at,x_coordinate,y_coordinate,
 risk_level,processing_status,processed_at,recognized_license_plate
)
VALUES
(@p1,  @r1,'ILLEGAL_PARKING',       '소방 통로 불법 주차 감지','101동 주차장 A 소방시설 앞 정차 차량을 감지했습니다.',0.962,'2026-07-08 06:24:00',25.200,19.100,'NORMAL','COMPLETED','2026-07-08 06:41:00','45더 9182'),
(@p1,  @r1,'TRASH_DETECTED',        '보행로 적치물 발견','정문 보행로 우측에 대형 종이 상자가 방치되어 있습니다.',0.913,'2026-07-08 06:49:00',14.800,31.600,'LOW','COMPLETED','2026-07-08 07:03:00',NULL),
(@p1+1,@r2,'UNREGISTERED_VEHICLE',  '미등록 차량 출입 확인','등록 차량 목록에 없는 차량이 주차장 B에 진입했습니다.',0.944,'2026-07-12 21:26:00',49.700,19.800,'NORMAL','COMPLETED','2026-07-12 21:48:00','27수 6419'),
(@p1+2,@r3,'RECYCLING_AREA_FULL',   '분리수거장 적재량 초과','재활용품 적재량이 수거 기준선을 초과했습니다.',0.938,'2026-07-18 14:37:00',69.100,22.400,'NORMAL','COMPLETED','2026-07-18 15:02:00',NULL),
(@p1+2,@r3,'EMERGENCY',             '주차장 C 낙상 의심 상황','주차장 C 보행 구역에서 장시간 움직임이 없는 사람을 감지했습니다.',0.981,'2026-07-18 14:53:00',36.500,46.200,'EMERGENCY','COMPLETED','2026-07-18 15:04:00',NULL),
(@p1+3,@r1,'ILLEGAL_PARKING',       '장애인 전용구역 주차 위반','장애인 표지가 확인되지 않은 차량이 전용 구역에 주차했습니다.',0.957,'2026-07-23 06:11:00',27.400,17.900,'NORMAL','PROCESSING',NULL,'91하 3027'),
(@p1+4,@r4,'TRASH_DETECTED',        '후문 화단 폐기물 발견','후문 진입로 화단 옆에 검은 봉투 두 개가 놓여 있습니다.',0.889,'2026-07-29 22:46:00',72.100,53.200,'LOW','COMPLETED','2026-07-29 23:02:00',NULL),
(@p1+4,@r4,'UNREGISTERED_VEHICLE',  '방문 등록 미확인 차량','방문 예약 내역이 없는 차량의 장시간 주차를 확인했습니다.',0.925,'2026-07-29 23:08:00',46.300,20.600,'NORMAL','DETECTED',NULL,'68루 5514'),
(@p1+5,@r2,'RECYCLING_AREA_FULL',   '일반 폐기물 수거 요청','일반 폐기물 보관 구역의 적재율이 90%를 넘었습니다.',0.946,'2026-08-01 06:44:00',68.600,22.100,'NORMAL','COMPLETED','2026-08-01 07:05:00',NULL),
(@p1+5,@r2,'ILLEGAL_PARKING',       '주차장 회차로 정차 차량','주차장 A 회차로에 15분 이상 정차 중인 차량을 감지했습니다.',0.932,'2026-08-01 07:02:00',29.200,21.500,'NORMAL','COMPLETED','2026-08-01 07:19:00','34어 7825'),
(@p1+6,@r3,'TRASH_DETECTED',        '공용 출입구 생활 폐기물','102동 공동현관 옆에 생활 폐기물이 방치되어 있습니다.',0.901,'2026-08-02 14:06:00',52.800,35.400,'LOW','PROCESSING',NULL,NULL),
(@p1+7,@r1,'EMERGENCY',             '주차장 연기 감지','주차장 B 전기 설비 인근에서 연기 형태와 이상 움직임을 감지했습니다.',0.987,'2026-08-03 21:34:00',54.200,24.800,'EMERGENCY','COMPLETED','2026-08-03 21:43:00',NULL),
(@p1+7,@r1,'UNREGISTERED_VEHICLE',  '심야 미등록 차량 확인','차량 등록 및 방문 승인 내역이 확인되지 않습니다.',0.918,'2026-08-03 21:58:00',43.700,18.300,'NORMAL','DETECTED',NULL,'19조 8462'),
(@p1+8,@r4,'RECYCLING_AREA_FULL',   '재활용품 수거함 포화','투명 페트병 수거함의 적재 공간이 부족합니다.',0.951,'2026-08-04 06:24:00',70.200,23.000,'NORMAL','PROCESSING',NULL,NULL),
(@p1+9,@r2,'ILLEGAL_PARKING',       '정문 비상차로 주차 감지','비상차량 진입 구간에 승용차가 정차해 있습니다.',0.969,'2026-08-05 21:08:00',10.400,9.700,'NORMAL','DETECTED',NULL,'52도 1908'),
(@p1+9,@r2,'TRASH_DETECTED',        '주차장 C 유리병 발견','주차장 C 보행 통로에서 깨진 유리병을 감지했습니다.',0.955,'2026-08-05 21:31:00',39.500,48.100,'EMERGENCY','PROCESSING',NULL,NULL),
-- 대시보드 최근 미완료 이벤트: 5개 유형이 최신 목록에 모두 보이도록 현재 시각 기준으로 배치
(NULL,@r4,'EMERGENCY',             '주차장 비상 호출 감지','주차장 A 비상 호출 구역에서 도움 요청 신호가 감지되었습니다.',0.991,DATE_SUB(NOW(6),INTERVAL 1 MINUTE),25.800,20.100,'EMERGENCY','DETECTED',NULL,NULL),
(NULL,@r3,'RECYCLING_AREA_FULL',   '재활용 수거 구역 포화','재활용 수거 구역의 적재량이 안전 기준을 초과하여 수거 확인 중입니다.',0.953,DATE_SUB(NOW(6),INTERVAL 3 MINUTE),69.500,22.700,'NORMAL','PROCESSING',NULL,NULL),
(NULL,@r1,'TRASH_DETECTED',        '주차장 C 폐기물 감지','주차장 C 진입로에 생활 폐기물이 방치되어 있습니다.',0.927,DATE_SUB(NOW(6),INTERVAL 5 MINUTE),37.200,47.600,'LOW','DETECTED',NULL,NULL),
(NULL,@r2,'UNREGISTERED_VEHICLE',  '정문 미등록 차량 진입','정문으로 진입한 차량의 입주민 및 방문 등록 내역을 확인 중입니다.',0.948,DATE_SUB(NOW(6),INTERVAL 7 MINUTE),10.300,9.400,'NORMAL','PROCESSING',NULL,'77두 3158'),
(NULL,@r1,'ILLEGAL_PARKING',       '소방차 전용구역 주차 감지','소방차 전용구역에 정차된 차량이 확인되었습니다.',0.973,DATE_SUB(NOW(6),INTERVAL 9 MINUTE),24.600,18.900,'NORMAL','DETECTED',NULL,'29호 6842'),
-- 분리수거장 포화 상태를 품목과 처리 단계별로 다양하게 구성
(NULL,@r3,'RECYCLING_AREA_FULL',   '종이류 적재 구역 포화','분리수거장 종이류 적재 구역이 가득 차 추가 배출이 어려운 상태입니다.',0.966,DATE_SUB(NOW(6),INTERVAL 13 MINUTE),68.700,21.900,'NORMAL','DETECTED',NULL,NULL),
(NULL,@r4,'RECYCLING_AREA_FULL',   '플라스틱 수거함 포화','플라스틱 수거함의 적재율이 95%를 넘어 수거 업체에 회수 요청을 전달했습니다.',0.958,DATE_SUB(NOW(6),INTERVAL 1 DAY),70.500,23.400,'NORMAL','PROCESSING',NULL,NULL),
(NULL,@r1,'RECYCLING_AREA_FULL',   '캔 수거함 포화 조치 완료','캔 수거함 포화 상태를 확인하고 신규 수거함으로 교체했습니다.',0.949,DATE_SUB(NOW(6),INTERVAL 2 DAY),69.800,22.600,'NORMAL','COMPLETED',DATE_SUB(NOW(6),INTERVAL 2 DAY),NULL);

-- 순찰 상세의 지점 기록이 풍부하게 보이도록 완료 순찰마다 이벤트를 2건씩 추가한다.
INSERT INTO detected_events (
 patrol_id,robot_id,event_type,event_title,event_details,confidence,occurred_at,x_coordinate,y_coordinate,
 risk_level,processing_status,processed_at,recognized_license_plate
)
VALUES
(@p1,@r1,'UNREGISTERED_VEHICLE','주차장 A 미등록 차량 확인','순찰 중 방문 등록 내역이 없는 차량을 확인했습니다.',0.934,'2026-07-08 06:17:00',25.000,18.000,'NORMAL','COMPLETED','2026-07-08 06:29:00','18고 4721'),
(@p1,@r1,'RECYCLING_AREA_FULL','종이 수거함 적재 확인','종이 수거함의 적재량이 관리 기준을 초과했습니다.',0.922,'2026-07-08 06:42:00',68.000,21.000,'NORMAL','COMPLETED','2026-07-08 06:56:00',NULL),
(@p1+1,@r2,'ILLEGAL_PARKING','주차장 B 통행로 주차','주차장 B 통행 구간을 막고 있는 차량을 감지했습니다.',0.951,'2026-07-12 21:18:00',48.000,18.000,'NORMAL','COMPLETED','2026-07-12 21:31:00','42마 8163'),
(@p1+1,@r2,'TRASH_DETECTED','후문 진입로 폐기물','후문 진입로 가장자리에 방치된 봉투를 발견했습니다.',0.905,'2026-07-12 21:48:00',72.000,52.000,'LOW','COMPLETED','2026-07-12 21:59:00',NULL),
(@p1+2,@r3,'ILLEGAL_PARKING','주차장 A 이중 주차','주차장 A에서 차량 이동을 방해하는 이중 주차를 확인했습니다.',0.947,'2026-07-18 14:16:00',26.000,19.000,'NORMAL','COMPLETED','2026-07-18 14:28:00','63버 2904'),
(@p1+2,@r3,'TRASH_DETECTED','주차장 B 보행로 적치물','주차장 B 보행 구역에 놓인 종이 상자를 발견했습니다.',0.916,'2026-07-18 14:31:00',47.000,18.000,'LOW','COMPLETED','2026-07-18 14:46:00',NULL),
(@p1+3,@r1,'UNREGISTERED_VEHICLE','주차장 C 장기 주차 확인','등록 내역이 없는 차량의 장시간 주차를 확인했습니다.',0.939,'2026-07-23 06:09:00',36.000,45.000,'NORMAL','COMPLETED','2026-07-23 06:22:00','55서 7318'),
(@p1+3,@r1,'TRASH_DETECTED','후문 화단 쓰레기','후문 화단 주변에 소형 생활 쓰레기가 방치되어 있습니다.',0.898,'2026-07-23 06:38:00',71.000,51.000,'LOW','COMPLETED','2026-07-23 06:49:00',NULL),
(@p1+4,@r4,'ILLEGAL_PARKING','주차장 B 소방구역 정차','소방 설비 접근 구역에 정차된 차량을 확인했습니다.',0.963,'2026-07-29 22:27:00',49.000,18.000,'NORMAL','COMPLETED','2026-07-29 22:39:00','31주 6045'),
(@p1+4,@r4,'RECYCLING_AREA_FULL','병류 수거함 포화','병류 수거함이 가득 차 추가 수거가 필요한 상태입니다.',0.941,'2026-07-29 22:55:00',68.000,21.000,'NORMAL','COMPLETED','2026-07-29 23:08:00',NULL),
(@p1+5,@r2,'UNREGISTERED_VEHICLE','주차장 A 방문 미확인 차량','방문 차량 등록 목록에서 번호가 확인되지 않았습니다.',0.936,'2026-08-01 06:27:00',25.000,18.000,'NORMAL','COMPLETED','2026-08-01 06:41:00','24더 9380'),
(@p1+5,@r2,'TRASH_DETECTED','분리수거장 주변 적치물','분리수거장 통행로에 빈 상자가 쌓여 있습니다.',0.912,'2026-08-01 06:51:00',67.000,21.000,'LOW','COMPLETED','2026-08-01 07:03:00',NULL),
(@p1+6,@r3,'ILLEGAL_PARKING','주차장 B 회차구역 정차','회차구역에 장시간 정차 중인 차량을 감지했습니다.',0.956,'2026-08-02 13:52:00',48.000,18.000,'NORMAL','COMPLETED','2026-08-02 14:04:00','70누 1526'),
(@p1+6,@r3,'TRASH_DETECTED','주차장 C 음료 용기','주차장 C 벽면에 버려진 음료 용기를 발견했습니다.',0.904,'2026-08-02 14:19:00',36.000,45.000,'LOW','COMPLETED','2026-08-02 14:31:00',NULL),
(@p1+7,@r1,'UNREGISTERED_VEHICLE','정문 차량 등록 대조','정문 진입 차량의 등록 정보를 확인했습니다.',0.943,'2026-08-03 21:13:00',9.000,9.000,'NORMAL','COMPLETED','2026-08-03 21:24:00','16소 5837'),
(@p1+7,@r1,'RECYCLING_AREA_FULL','재활용품 임시 적재 초과','수거 예정 재활용품이 임시 적재선을 넘었습니다.',0.948,'2026-08-03 21:42:00',68.000,21.000,'NORMAL','COMPLETED','2026-08-03 21:55:00',NULL),
(@p1+8,@r4,'ILLEGAL_PARKING','후문 안전구역 정차','후문 안전 표지 구역에 정차된 차량을 확인했습니다.',0.952,'2026-08-04 06:13:00',72.000,52.000,'NORMAL','COMPLETED','2026-08-04 06:25:00','48도 3279'),
(@p1+8,@r4,'TRASH_DETECTED','주차장 B 비닐 봉투','주차장 B 기둥 옆에 방치된 비닐 봉투를 감지했습니다.',0.907,'2026-08-04 06:39:00',48.000,18.000,'LOW','COMPLETED','2026-08-04 06:51:00',NULL),
(@p1+9,@r2,'UNREGISTERED_VEHICLE','주차장 A 미등록 승용차','입주민 및 방문 차량 목록에 없는 승용차를 확인했습니다.',0.945,'2026-08-05 20:56:00',25.000,18.000,'NORMAL','COMPLETED','2026-08-05 21:09:00','82라 4601'),
(@p1+9,@r2,'RECYCLING_AREA_FULL','페트병 수거함 포화','페트병 수거함이 가득 차 수거가 필요한 상태입니다.',0.954,'2026-08-05 21:24:00',68.000,21.000,'NORMAL','COMPLETED','2026-08-05 21:38:00',NULL);

UPDATE patrols p
SET detected_event_count=(SELECT COUNT(*) FROM detected_events e WHERE e.patrol_id=p.patrol_id)
WHERE p.patrol_id BETWEEN @p1 AND @p1+9;

-- 이벤트 ID를 제목으로 안전하게 조회한다.
SET @e_illegal=(SELECT event_id FROM detected_events WHERE robot_id=@r2 AND event_title='정문 비상차로 주차 감지');
SET @e_vehicle=(SELECT event_id FROM detected_events WHERE robot_id=@r1 AND event_title='심야 미등록 차량 확인');
SET @e_trash=(SELECT event_id FROM detected_events WHERE robot_id=@r2 AND event_title='주차장 C 유리병 발견');
SET @e_recycle=(SELECT event_id FROM detected_events WHERE robot_id=@r4 AND event_title='재활용품 수거함 포화');
SET @e_emergency=(SELECT event_id FROM detected_events WHERE robot_id=@r1 AND event_title='주차장 연기 감지');
SET @e_dash_emergency=(SELECT event_id FROM detected_events WHERE event_title='주차장 비상 호출 감지' AND robot_id=@r4);
SET @e_dash_recycle=(SELECT event_id FROM detected_events WHERE event_title='재활용 수거 구역 포화' AND robot_id=@r3);
SET @e_dash_trash=(SELECT event_id FROM detected_events WHERE event_title='주차장 C 폐기물 감지' AND robot_id=@r1);
SET @e_dash_vehicle=(SELECT event_id FROM detected_events WHERE event_title='정문 미등록 차량 진입' AND robot_id=@r2);
SET @e_dash_illegal=(SELECT event_id FROM detected_events WHERE event_title='소방차 전용구역 주차 감지' AND robot_id=@r1);
SET @e_recycle_paper=(SELECT event_id FROM detected_events WHERE event_title='종이류 적재 구역 포화' AND robot_id=@r3);
SET @e_recycle_plastic=(SELECT event_id FROM detected_events WHERE event_title='플라스틱 수거함 포화' AND robot_id=@r4);
SET @e_recycle_can=(SELECT event_id FROM detected_events WHERE event_title='캔 수거함 포화 조치 완료' AND robot_id=@r1);

-- 이벤트 상세 이미지: backend/uploads/evidence의 실제 PNG 파일과 연결한다.
INSERT INTO event_evidence (event_id,media_type,file_url,captured_at,created_at,updated_at)
VALUES
(@e_illegal,'IMAGE','/api/uploads/evidence/illegal-parking-wide.png','2026-08-05 21:08:04',NOW(6),NOW(6)),
(@e_vehicle,'IMAGE','/api/uploads/evidence/unregistered-vehicle-wide.png','2026-08-03 21:58:07',NOW(6),NOW(6)),
(@e_trash,'IMAGE','/api/uploads/evidence/trash-detected-wide.png','2026-08-05 21:31:10',NOW(6),NOW(6)),
(@e_recycle,'IMAGE','/api/uploads/evidence/recycling-overflow-wide.png','2026-08-04 06:24:08',NOW(6),NOW(6)),
(@e_emergency,'IMAGE','/api/uploads/evidence/emergency-person-detected-wide.png','2026-08-03 21:34:03',NOW(6),NOW(6)),
(@e_dash_emergency,'IMAGE','/api/uploads/evidence/emergency-person-detected-wide.png',DATE_SUB(NOW(6),INTERVAL 1 MINUTE),NOW(6),NOW(6)),
(@e_dash_recycle,'IMAGE','/api/uploads/evidence/recycling-overflow-wide.png',DATE_SUB(NOW(6),INTERVAL 3 MINUTE),NOW(6),NOW(6)),
(@e_dash_trash,'IMAGE','/api/uploads/evidence/trash-detected-wide.png',DATE_SUB(NOW(6),INTERVAL 5 MINUTE),NOW(6),NOW(6)),
(@e_dash_vehicle,'IMAGE','/api/uploads/evidence/unregistered-vehicle-wide.png',DATE_SUB(NOW(6),INTERVAL 7 MINUTE),NOW(6),NOW(6)),
(@e_dash_illegal,'IMAGE','/api/uploads/evidence/illegal-parking-wide.png',DATE_SUB(NOW(6),INTERVAL 9 MINUTE),NOW(6),NOW(6)),
(@e_recycle_paper,'IMAGE','/api/uploads/evidence/recycling-overflow-wide.png',DATE_SUB(NOW(6),INTERVAL 13 MINUTE),NOW(6),NOW(6)),
(@e_recycle_plastic,'IMAGE','/api/uploads/evidence/recycling-overflow-wide.png',DATE_SUB(NOW(6),INTERVAL 1 DAY),NOW(6),NOW(6)),
(@e_recycle_can,'IMAGE','/api/uploads/evidence/recycling-overflow-wide.png',DATE_SUB(NOW(6),INTERVAL 2 DAY),NOW(6),NOW(6));

-- 이벤트 처리 타임라인: 감지→처리 중→완료 흐름과 담당 경비원 이름이 표시된다.
-- 모든 이벤트에 최신 담당자가 존재하도록 같은 단지 경비원 4명에게 고르게 배정한다.
INSERT INTO event_processing_history (
 event_id,processing_member_id,changed_processing_status,processing_note,changed_at,created_at,updated_at
)
SELECT e.event_id,
       CASE MOD(e.event_id,4)
           WHEN 0 THEN @guard_1 WHEN 1 THEN @guard_2 WHEN 2 THEN @guard_3 ELSE @guard_4
       END,
       e.processing_status,
       CASE e.processing_status
           WHEN 'DETECTED' THEN '관제 화면에서 이벤트를 확인하고 담당 구역을 점검 중입니다.'
           WHEN 'PROCESSING' THEN '현장 상황을 확인하고 필요한 안전 조치를 진행하고 있습니다.'
           ELSE '현장 확인과 후속 조치를 완료했습니다.'
       END,
       DATE_ADD(e.occurred_at,INTERVAL 1 MINUTE),
       DATE_ADD(e.occurred_at,INTERVAL 1 MINUTE),
       DATE_ADD(e.occurred_at,INTERVAL 1 MINUTE)
FROM detected_events e
JOIN patrol_robots r ON r.robot_id=e.robot_id
WHERE r.apartment_complex_id=@complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

INSERT INTO event_processing_history (event_id,processing_member_id,changed_processing_status,processing_note,changed_at,created_at,updated_at)
VALUES
(@e_illegal,@guard_1,'DETECTED','관제 화면에서 비상차로 정차 차량을 확인했습니다.','2026-08-05 21:08:10','2026-08-05 21:08:10','2026-08-05 21:08:10'),
(@e_vehicle,@guard_2,'DETECTED','차량 번호와 방문 예약 내역을 대조했습니다.','2026-08-03 21:58:15','2026-08-03 21:58:15','2026-08-03 21:58:15'),
(@e_trash,@guard_3,'DETECTED','위험 폐기물 위치를 확인했습니다.','2026-08-05 21:31:15','2026-08-05 21:31:15','2026-08-05 21:31:15'),
(@e_trash,@guard_3,'PROCESSING','현장 대원에게 안전 통제와 수거를 요청했습니다.','2026-08-05 21:34:00','2026-08-05 21:34:00','2026-08-05 21:34:00'),
(@e_recycle,@guard_4,'DETECTED','수거함 적재 상태를 확인했습니다.','2026-08-04 06:24:12','2026-08-04 06:24:12','2026-08-04 06:24:12'),
(@e_recycle,@guard_4,'PROCESSING','환경 관리 업체에 당일 수거를 요청했습니다.','2026-08-04 06:31:00','2026-08-04 06:31:00','2026-08-04 06:31:00'),
(@e_emergency,@guard_2,'DETECTED','긴급 이벤트 영상과 위치를 확인했습니다.','2026-08-03 21:34:06','2026-08-03 21:34:06','2026-08-03 21:34:06'),
(@e_emergency,@guard_3,'PROCESSING','현장 확인과 소방 설비 점검을 요청했습니다.','2026-08-03 21:36:00','2026-08-03 21:36:00','2026-08-03 21:36:00'),
(@e_emergency,@guard_4,'COMPLETED','설비실 수증기로 확인되어 현장 환기 후 조치 완료했습니다.','2026-08-03 21:43:00','2026-08-03 21:43:00','2026-08-03 21:43:00');

-- 알림 기록: SENT/PENDING/FAILED가 모두 목록과 상세에 표시된다.
INSERT INTO notifications (event_id,recipient_resident_id,notification_content,send_status,sent_at,created_at,updated_at)
VALUES
(@e_illegal,@resident_1,'101동 비상차로 주차 차량이 확인되었습니다. 안전한 이동 주차를 부탁드립니다.','SENT','2026-08-05 21:10:00','2026-08-05 21:09:42','2026-08-05 21:10:00'),
(@e_vehicle,@resident_2,'단지 내 미등록 차량이 확인되어 방문 승인 여부를 확인하고 있습니다.','SENT','2026-08-03 22:00:00','2026-08-03 21:59:20','2026-08-03 22:00:00'),
(@e_trash,@resident_3,'주차장 C 보행 통로에 위험 물질이 발견되어 현장 조치 중입니다.','SENT','2026-08-05 21:35:00','2026-08-05 21:34:40','2026-08-05 21:35:00'),
(@e_recycle,@resident_1,'재활용 수거함 포화로 수거 요청이 접수되었습니다.','PENDING',NULL,'2026-08-04 06:31:30','2026-08-04 06:31:30'),
(@e_emergency,@resident_2,'주차장 이상 징후가 감지되어 관리 인력이 현장을 확인했습니다.','SENT','2026-08-03 21:37:00','2026-08-03 21:36:30','2026-08-03 21:37:00'),
(@e_emergency,@resident_3,'주차장 안전 점검 안내 발송이 통신 문제로 완료되지 않았습니다.','FAILED',NULL,'2026-08-03 21:36:32','2026-08-03 21:38:00');

-- 현재 서비스 날짜(2026-08-06)에서 조회되는 직전 주/직전 달 AI 인사이트
INSERT INTO analytics_ai_insights (
 apartment_complex_id,period_type,period_key,period_from,period_to,generation_status,insight_content,created_at,updated_at
)
VALUES
(@complex_id,'WEEK','2026-W31','2026-07-27 00:00:00','2026-08-02 23:59:59.999999','COMPLETED',
 '지난주에는 야간과 이른 아침 시간대에 주차 관련 이벤트가 집중되었습니다. 주차장 A·B와 후문 진입로의 순찰 빈도를 유지하고, 분리수거장 적재 상태를 오전 순찰에서 우선 확인하는 것이 좋습니다.',NOW(6),NOW(6)),
(@complex_id,'MONTH','2026-07','2026-07-01 00:00:00','2026-07-31 23:59:59.999999','COMPLETED',
 '7월 순찰은 주요 구역을 안정적으로 포함했습니다. 불법 주차와 미등록 차량이 전체 이벤트의 높은 비중을 차지했으며, 21시 이후 주차 구역에서 반복되는 경향이 나타났습니다. 야간 순찰 시 주차장과 후문 확인을 강화하는 것을 권장합니다.',NOW(6),NOW(6))
ON DUPLICATE KEY UPDATE generation_status='COMPLETED',insight_content=VALUES(insight_content),updated_at=NOW(6);

COMMIT;

-- -----------------------------------------------------------------------------
-- 실행 결과 검증: 각 화면에 필요한 데이터 수와 단지당 지도 1개 여부 확인
-- -----------------------------------------------------------------------------
SELECT 'robots' category, COUNT(*) count_value FROM patrol_robots WHERE apartment_complex_id=@complex_id AND robot_serial_number LIKE 'RO-Ki%'
UNION ALL SELECT 'maps',COUNT(*) FROM patrol_maps WHERE apartment_complex_id=@complex_id
UNION ALL SELECT 'checkpoints',COUNT(*) FROM checkpoints WHERE map_id=@map_id
UNION ALL SELECT 'patrols',COUNT(*) FROM patrols p JOIN patrol_robots r ON r.robot_id=p.robot_id WHERE r.apartment_complex_id=@complex_id AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042')
UNION ALL SELECT 'events',COUNT(*) FROM detected_events e JOIN patrol_robots r ON r.robot_id=e.robot_id WHERE r.apartment_complex_id=@complex_id AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042')
UNION ALL SELECT 'notifications',COUNT(*) FROM notifications n JOIN detected_events e ON e.event_id=n.event_id JOIN patrol_robots r ON r.robot_id=e.robot_id WHERE r.apartment_complex_id=@complex_id AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042');

SELECT event_type, processing_status, risk_level, COUNT(*) event_count
FROM detected_events e
JOIN patrol_robots r ON r.robot_id=e.robot_id
WHERE r.apartment_complex_id=@complex_id
  AND r.robot_serial_number IN ('RO-Ki3214','RO-Ki4728','RO-Ki5861','RO-Ki7395','RO-Ki8042')
GROUP BY event_type, processing_status, risk_level
ORDER BY event_type, processing_status;
