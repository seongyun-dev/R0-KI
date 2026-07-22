ALTER TABLE patrol_robots
    ADD COLUMN camera_status VARCHAR(20) AFTER battery_level;

ALTER TABLE patrol_robots
    ADD COLUMN lidar_status VARCHAR(20) AFTER camera_status;

ALTER TABLE patrol_robots
    ADD COLUMN motor_status VARCHAR(20) AFTER lidar_status;

ALTER TABLE patrol_robots
    ADD COLUMN status_reported_at TIMESTAMP(6) AFTER motor_status;
