ALTER TABLE checkpoints
    ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX idx_checkpoints_map_active
    ON checkpoints (map_id, active);

CREATE TABLE navigation_waypoints (
    waypoint_id BIGINT NOT NULL AUTO_INCREMENT,
    map_id BIGINT NOT NULL,
    map_version INT NOT NULL,
    waypoint_sequence INT NOT NULL,
    x_coordinate DECIMAL(10, 3) NOT NULL,
    y_coordinate DECIMAL(10, 3) NOT NULL,
    action VARCHAR(20) NOT NULL,
    yaw DECIMAL(7, 4),
    acceptance_radius DECIMAL(5, 3) NOT NULL DEFAULT 0.300,
    zone_id BIGINT,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_navigation_waypoints PRIMARY KEY (waypoint_id),
    CONSTRAINT uk_navigation_waypoints_map_version_sequence
        UNIQUE (map_id, map_version, waypoint_sequence),
    CONSTRAINT chk_navigation_waypoints_acceptance_radius
        CHECK (acceptance_radius >= 0.200 AND acceptance_radius <= 1.000),
    CONSTRAINT fk_navigation_waypoints_patrol_map
        FOREIGN KEY (map_id) REFERENCES patrol_maps (map_id),
    CONSTRAINT fk_navigation_waypoints_zone
        FOREIGN KEY (zone_id) REFERENCES checkpoints (checkpoint_id)
);

CREATE INDEX idx_navigation_waypoints_map_version
    ON navigation_waypoints (map_id, map_version);

CREATE INDEX idx_navigation_waypoints_zone_id
    ON navigation_waypoints (zone_id);
