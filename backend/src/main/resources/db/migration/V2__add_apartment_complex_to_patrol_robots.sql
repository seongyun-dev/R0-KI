ALTER TABLE patrol_robots
    ADD COLUMN apartment_complex_id BIGINT NOT NULL AFTER robot_id;

ALTER TABLE patrol_robots
    ADD CONSTRAINT fk_patrol_robots_apartment_complex
        FOREIGN KEY (apartment_complex_id)
        REFERENCES apartment_complexes (apartment_complex_id);

CREATE INDEX idx_patrol_robots_apartment_complex_id
    ON patrol_robots (apartment_complex_id);
