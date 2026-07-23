CREATE TABLE apartment_complexes (
    apartment_complex_id BIGINT NOT NULL AUTO_INCREMENT,
    apartment_name VARCHAR(100) NOT NULL,
    address VARCHAR(200) NOT NULL,
    postal_code VARCHAR(10),
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_apartment_complexes PRIMARY KEY (apartment_complex_id)
);

CREATE TABLE members (
    member_id BIGINT NOT NULL AUTO_INCREMENT,
    apartment_complex_id BIGINT NOT NULL,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(50) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    member_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_members PRIMARY KEY (member_id),
    CONSTRAINT uk_members_username UNIQUE (username),
    CONSTRAINT fk_members_apartment_complex
        FOREIGN KEY (apartment_complex_id)
        REFERENCES apartment_complexes (apartment_complex_id)
);

CREATE INDEX idx_members_apartment_complex_id
    ON members (apartment_complex_id);

CREATE TABLE residents (
    resident_id BIGINT NOT NULL AUTO_INCREMENT,
    apartment_complex_id BIGINT NOT NULL,
    name VARCHAR(50) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    building_number VARCHAR(20) NOT NULL,
    unit_number VARCHAR(20) NOT NULL,
    kakao_notification_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_residents PRIMARY KEY (resident_id),
    CONSTRAINT uk_residents_unit_phone
        UNIQUE (apartment_complex_id, building_number, unit_number, phone_number),
    CONSTRAINT fk_residents_apartment_complex
        FOREIGN KEY (apartment_complex_id)
        REFERENCES apartment_complexes (apartment_complex_id)
);

CREATE INDEX idx_residents_apartment_complex_id
    ON residents (apartment_complex_id);

CREATE TABLE registered_vehicles (
    vehicle_id BIGINT NOT NULL AUTO_INCREMENT,
    resident_id BIGINT NOT NULL,
    license_plate VARCHAR(20) NOT NULL,
    disabled_vehicle BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_registered_vehicles PRIMARY KEY (vehicle_id),
    CONSTRAINT uk_registered_vehicles_license_plate UNIQUE (license_plate),
    CONSTRAINT fk_registered_vehicles_resident
        FOREIGN KEY (resident_id)
        REFERENCES residents (resident_id)
);

CREATE INDEX idx_registered_vehicles_resident_id
    ON registered_vehicles (resident_id);

CREATE TABLE patrol_maps (
    map_id BIGINT NOT NULL AUTO_INCREMENT,
    apartment_complex_id BIGINT NOT NULL,
    map_name VARCHAR(255) NOT NULL,
    map_url VARCHAR(1000) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_patrol_maps PRIMARY KEY (map_id),
    CONSTRAINT fk_patrol_maps_apartment_complex
        FOREIGN KEY (apartment_complex_id)
        REFERENCES apartment_complexes (apartment_complex_id)
);

CREATE INDEX idx_patrol_maps_apartment_complex_id
    ON patrol_maps (apartment_complex_id);

CREATE TABLE checkpoints (
    checkpoint_id BIGINT NOT NULL AUTO_INCREMENT,
    map_id BIGINT NOT NULL,
    checkpoint_type VARCHAR(30) NOT NULL,
    min_x DECIMAL(10, 3) NOT NULL,
    min_y DECIMAL(10, 3) NOT NULL,
    max_x DECIMAL(10, 3) NOT NULL,
    max_y DECIMAL(10, 3) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_checkpoints PRIMARY KEY (checkpoint_id),
    CONSTRAINT fk_checkpoints_patrol_map
        FOREIGN KEY (map_id)
        REFERENCES patrol_maps (map_id)
);

CREATE INDEX idx_checkpoints_map_id
    ON checkpoints (map_id);

CREATE TABLE patrol_robots (
    robot_id BIGINT NOT NULL AUTO_INCREMENT,
    robot_name VARCHAR(100) NOT NULL,
    robot_serial_number VARCHAR(100) NOT NULL,
    x_coordinate DECIMAL(10, 3),
    y_coordinate DECIMAL(10, 3),
    location_updated_at TIMESTAMP(6),
    robot_status VARCHAR(20) NOT NULL DEFAULT 'IDLE',
    battery_level DECIMAL(5, 2),
    last_connected_at TIMESTAMP(6),
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_patrol_robots PRIMARY KEY (robot_id),
    CONSTRAINT uk_patrol_robots_serial_number UNIQUE (robot_serial_number)
);

CREATE TABLE patrols (
    patrol_id BIGINT NOT NULL AUTO_INCREMENT,
    robot_id BIGINT NOT NULL,
    patrol_status VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS',
    patrol_started_at TIMESTAMP(6),
    patrol_ended_at TIMESTAMP(6),
    total_duration INT,
    detected_event_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_patrols PRIMARY KEY (patrol_id),
    CONSTRAINT fk_patrols_robot
        FOREIGN KEY (robot_id)
        REFERENCES patrol_robots (robot_id)
);

CREATE INDEX idx_patrols_robot_id
    ON patrols (robot_id);

CREATE INDEX idx_patrols_status_started_at
    ON patrols (patrol_status, patrol_started_at);

CREATE TABLE route_positions (
    position_id BIGINT NOT NULL AUTO_INCREMENT,
    patrol_id BIGINT NOT NULL,
    x_coordinate DECIMAL(10, 3) NOT NULL,
    y_coordinate DECIMAL(10, 3) NOT NULL,
    recorded_at TIMESTAMP(6) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_route_positions PRIMARY KEY (position_id),
    CONSTRAINT fk_route_positions_patrol
        FOREIGN KEY (patrol_id)
        REFERENCES patrols (patrol_id)
);

CREATE INDEX idx_route_positions_patrol_recorded_at
    ON route_positions (patrol_id, recorded_at);

CREATE TABLE patrol_reports (
    report_id BIGINT NOT NULL AUTO_INCREMENT,
    patrol_id BIGINT NOT NULL,
    report_title VARCHAR(200) NOT NULL,
    patrol_summary TEXT,
    report_content TEXT,
    total_event_count INT NOT NULL DEFAULT 0,
    emergency_event_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_patrol_reports PRIMARY KEY (report_id),
    CONSTRAINT uk_patrol_reports_patrol_id UNIQUE (patrol_id),
    CONSTRAINT fk_patrol_reports_patrol
        FOREIGN KEY (patrol_id)
        REFERENCES patrols (patrol_id)
);

CREATE TABLE detected_events (
    event_id BIGINT NOT NULL AUTO_INCREMENT,
    patrol_id BIGINT,
    robot_id BIGINT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    event_title VARCHAR(200) NOT NULL,
    event_details TEXT,
    occurred_at TIMESTAMP(6) NOT NULL,
    x_coordinate DECIMAL(10, 3),
    y_coordinate DECIMAL(10, 3),
    risk_level VARCHAR(20) NOT NULL,
    processing_status VARCHAR(20) NOT NULL DEFAULT 'DETECTED',
    processed_at TIMESTAMP(6),
    recognized_license_plate VARCHAR(20),
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_detected_events PRIMARY KEY (event_id),
    CONSTRAINT fk_detected_events_patrol
        FOREIGN KEY (patrol_id)
        REFERENCES patrols (patrol_id),
    CONSTRAINT fk_detected_events_robot
        FOREIGN KEY (robot_id)
        REFERENCES patrol_robots (robot_id)
);

CREATE INDEX idx_detected_events_patrol_id
    ON detected_events (patrol_id);

CREATE INDEX idx_detected_events_robot_id
    ON detected_events (robot_id);

CREATE INDEX idx_detected_events_status_occurred_at
    ON detected_events (processing_status, occurred_at);

CREATE TABLE event_evidence (
    evidence_id BIGINT NOT NULL AUTO_INCREMENT,
    event_id BIGINT NOT NULL,
    media_type VARCHAR(20) NOT NULL,
    file_url VARCHAR(1000) NOT NULL,
    captured_at TIMESTAMP(6),
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_event_evidence PRIMARY KEY (evidence_id),
    CONSTRAINT fk_event_evidence_event
        FOREIGN KEY (event_id)
        REFERENCES detected_events (event_id)
);

CREATE INDEX idx_event_evidence_event_id
    ON event_evidence (event_id);

CREATE TABLE event_processing_history (
    processing_history_id BIGINT NOT NULL AUTO_INCREMENT,
    event_id BIGINT NOT NULL,
    processing_member_id BIGINT,
    changed_processing_status VARCHAR(20) NOT NULL,
    processing_note VARCHAR(500),
    changed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_event_processing_history PRIMARY KEY (processing_history_id),
    CONSTRAINT fk_event_processing_history_event
        FOREIGN KEY (event_id)
        REFERENCES detected_events (event_id),
    CONSTRAINT fk_event_processing_history_member
        FOREIGN KEY (processing_member_id)
        REFERENCES members (member_id)
);

CREATE INDEX idx_event_processing_history_event_changed_at
    ON event_processing_history (event_id, changed_at);

CREATE INDEX idx_event_processing_history_member_id
    ON event_processing_history (processing_member_id);

CREATE TABLE notifications (
    notification_id BIGINT NOT NULL AUTO_INCREMENT,
    event_id BIGINT NOT NULL,
    recipient_resident_id BIGINT NOT NULL,
    notification_title VARCHAR(200) NOT NULL,
    notification_content TEXT NOT NULL,
    send_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    sent_at TIMESTAMP(6),
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_notifications PRIMARY KEY (notification_id),
    CONSTRAINT fk_notifications_event
        FOREIGN KEY (event_id)
        REFERENCES detected_events (event_id),
    CONSTRAINT fk_notifications_recipient_resident
        FOREIGN KEY (recipient_resident_id)
        REFERENCES residents (resident_id)
);

CREATE INDEX idx_notifications_event_id
    ON notifications (event_id);

CREATE INDEX idx_notifications_recipient_status
    ON notifications (recipient_resident_id, send_status);
