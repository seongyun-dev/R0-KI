-- V7: 로봇 상태 확장, 이벤트 신뢰도, 지도 좌표변환 필드 추가
-- 작성 기준: RO-KI IoT 연동 명세서 v2 논의 결과
-- robot_status/motor_status/camera_status/lidar_status는 VARCHAR라 값 목록을 DB가 강제하지 않음
-- (OBSTACLE_STOP, ERROR, DISCONNECTED 등 새 상태값은 Java enum에만 추가하면 되고 DB 마이그레이션 불필요)

--------------------------------------------------------------------------------
-- 1. patrol_robots — heading, line_sensor_status 추가
--------------------------------------------------------------------------------

ALTER TABLE patrol_robots
    ADD COLUMN heading DECIMAL(6,2) NULL COMMENT '로봇 진행방향(도), 0=지도 +X, 반시계 양수' AFTER y_coordinate;

ALTER TABLE patrol_robots
    ADD COLUMN line_sensor_status VARCHAR(20) NULL COMMENT '라인센서 상태' AFTER motor_status;

--------------------------------------------------------------------------------
-- 2. detected_events — confidence 추가
--------------------------------------------------------------------------------

ALTER TABLE detected_events
    ADD COLUMN confidence DECIMAL(4,3) NULL COMMENT 'AI 탐지 신뢰도(0.000~1.000), event_details에서 파싱하여 저장' AFTER event_details;

--------------------------------------------------------------------------------
-- 3. patrol_maps — SLAM 좌표변환 관련 필드 추가 (A담당 영역, 엔티티 매핑은 A가 진행)
--------------------------------------------------------------------------------

ALTER TABLE patrol_maps
    ADD COLUMN resolution DECIMAL(6,4) NULL COMMENT '지도 해상도(픽셀당 실제 미터)' AFTER map_url,
    ADD COLUMN origin_x DECIMAL(10,3) NULL COMMENT '지도 원점 X좌표(미터)' AFTER resolution,
    ADD COLUMN origin_y DECIMAL(10,3) NULL COMMENT '지도 원점 Y좌표(미터)' AFTER origin_x,
    ADD COLUMN origin_yaw DECIMAL(6,2) NULL COMMENT '지도 원점 회전각(도)' AFTER origin_y,
    ADD COLUMN width INT NULL COMMENT '지도 가로 크기(픽셀)' AFTER origin_yaw,
    ADD COLUMN height INT NULL COMMENT '지도 세로 크기(픽셀)' AFTER width,
    ADD COLUMN map_version INT NULL DEFAULT 1 COMMENT '지도 버전' AFTER height;
