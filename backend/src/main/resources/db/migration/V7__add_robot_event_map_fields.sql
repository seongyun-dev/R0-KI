ALTER TABLE patrol_robots
    ADD COLUMN heading DECIMAL(6,2) NULL AFTER y_coordinate;

ALTER TABLE patrol_robots
    ADD COLUMN line_sensor_status VARCHAR(20) NULL AFTER motor_status;

ALTER TABLE detected_events
    ADD COLUMN confidence DECIMAL(4,3) NULL AFTER event_details;

ALTER TABLE patrol_maps
    ADD COLUMN resolution DECIMAL(6,4) NULL AFTER map_url;

ALTER TABLE patrol_maps
    ADD COLUMN origin_x DECIMAL(10,3) NULL AFTER resolution;

ALTER TABLE patrol_maps
    ADD COLUMN origin_y DECIMAL(10,3) NULL AFTER origin_x;

ALTER TABLE patrol_maps
    ADD COLUMN origin_yaw DECIMAL(6,2) NULL AFTER origin_y;

ALTER TABLE patrol_maps
    ADD COLUMN width INT NULL AFTER origin_yaw;

ALTER TABLE patrol_maps
    ADD COLUMN height INT NULL AFTER width;

ALTER TABLE patrol_maps
    ADD COLUMN map_version INT NULL DEFAULT 1 AFTER height;
