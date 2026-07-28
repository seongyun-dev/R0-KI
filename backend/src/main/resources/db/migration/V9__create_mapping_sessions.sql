CREATE TABLE mapping_sessions (
    mapping_session_id BIGINT NOT NULL AUTO_INCREMENT,
    apartment_complex_id BIGINT NOT NULL,
    robot_id BIGINT NOT NULL,
    command_id VARCHAR(36) NOT NULL,
    mapping_status VARCHAR(20) NOT NULL DEFAULT 'REQUESTED',
    started_at TIMESTAMP(6),
    finished_at TIMESTAMP(6),
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_mapping_sessions PRIMARY KEY (mapping_session_id),
    CONSTRAINT uk_mapping_sessions_command_id UNIQUE (command_id),
    CONSTRAINT uk_mapping_sessions_apartment_complex UNIQUE (apartment_complex_id),
    CONSTRAINT uk_mapping_sessions_robot UNIQUE (robot_id),
    CONSTRAINT fk_mapping_sessions_apartment_complex
        FOREIGN KEY (apartment_complex_id) REFERENCES apartment_complexes (apartment_complex_id),
    CONSTRAINT fk_mapping_sessions_robot
        FOREIGN KEY (robot_id) REFERENCES patrol_robots (robot_id)
);

-- 지도 생성 요청 시 동일 로봇의 REQUESTED/MAPPING 세션 존재 여부를 빠르게 검사한다.
CREATE INDEX idx_mapping_sessions_robot_status
    ON mapping_sessions (robot_id, mapping_status);

ALTER TABLE patrol_maps
    ADD CONSTRAINT uk_patrol_maps_apartment_complex
        UNIQUE (apartment_complex_id);
