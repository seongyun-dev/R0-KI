ALTER TABLE checkpoints
    ADD COLUMN checkpoint_name VARCHAR(100);

UPDATE checkpoints
SET checkpoint_name = CASE checkpoint_type
    WHEN 'START' THEN '출발지'
    WHEN 'PARKING' THEN '주차장'
    WHEN 'RECYCLING_AREA' THEN '분리수거장'
    WHEN 'DANGER_ZONE' THEN '위험 구역'
    WHEN 'DESTINATION' THEN '도착지'
    ELSE '미지정 구역'
END;

ALTER TABLE checkpoints
    MODIFY COLUMN checkpoint_name VARCHAR(100) NOT NULL;
