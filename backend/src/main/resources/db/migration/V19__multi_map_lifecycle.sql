-- Multi-map lifecycle Phase 1.
-- 단지당 맵 N개 허용, active 포인터, 순찰 시작 시 맵 스냅샷.
-- UPDATE 구문은 H2(test) / MySQL(prod) 공통 서브쿼리 형태를 사용한다.

-- 1) 단지당 맵 1장 UNIQUE 제거 (V9).
ALTER TABLE patrol_maps
    DROP INDEX uk_patrol_maps_apartment_complex;

-- 2) 맵 라이프사이클 상태. 기존 행은 ACTIVE.
ALTER TABLE patrol_maps
    ADD COLUMN map_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';

ALTER TABLE patrol_maps
    ADD CONSTRAINT chk_patrol_maps_status
        CHECK (map_status IN ('ACTIVE', 'ARCHIVED'));

CREATE INDEX idx_patrol_maps_apartment_status
    ON patrol_maps (apartment_complex_id, map_status);

-- 3) 단지의 현재 사용 맵 포인터.
ALTER TABLE apartment_complexes
    ADD COLUMN active_map_id BIGINT NULL;

UPDATE apartment_complexes
SET active_map_id = (
    SELECT MIN(pm.map_id)
    FROM patrol_maps pm
    WHERE pm.apartment_complex_id = apartment_complexes.apartment_complex_id
);

ALTER TABLE apartment_complexes
    ADD CONSTRAINT fk_apartment_complexes_active_map
        FOREIGN KEY (active_map_id) REFERENCES patrol_maps (map_id);

-- 4) 순찰 시작 시점 맵 스냅샷 (레거시는 NULL 허용).
ALTER TABLE patrols
    ADD COLUMN map_id BIGINT NULL;

ALTER TABLE patrols
    ADD COLUMN map_version INT NULL;

UPDATE patrols
SET map_id = (
    SELECT ac.active_map_id
    FROM patrol_robots robot
    INNER JOIN apartment_complexes ac
        ON ac.apartment_complex_id = robot.apartment_complex_id
    WHERE robot.robot_id = patrols.robot_id
)
WHERE EXISTS (
    SELECT 1
    FROM patrol_robots robot
    INNER JOIN apartment_complexes ac
        ON ac.apartment_complex_id = robot.apartment_complex_id
    WHERE robot.robot_id = patrols.robot_id
      AND ac.active_map_id IS NOT NULL
);

UPDATE patrols
SET map_version = (
    SELECT pm.map_version
    FROM patrol_maps pm
    WHERE pm.map_id = patrols.map_id
)
WHERE map_id IS NOT NULL;

ALTER TABLE patrols
    ADD CONSTRAINT fk_patrols_patrol_map
        FOREIGN KEY (map_id) REFERENCES patrol_maps (map_id);

CREATE INDEX idx_patrols_map_id ON patrols (map_id);
