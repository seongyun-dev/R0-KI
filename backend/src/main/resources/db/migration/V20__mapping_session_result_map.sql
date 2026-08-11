-- Map upload idempotency: remember which map a completed mapping session produced.
ALTER TABLE mapping_sessions
    ADD COLUMN result_map_id BIGINT NULL;

ALTER TABLE mapping_sessions
    ADD CONSTRAINT fk_mapping_sessions_result_map
        FOREIGN KEY (result_map_id) REFERENCES patrol_maps (map_id);
