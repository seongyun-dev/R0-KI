ALTER TABLE mapping_sessions
    ADD COLUMN stop_command_id VARCHAR(36) NULL,
    ADD COLUMN stop_command_status VARCHAR(20) NULL,
    ADD COLUMN stop_failure_reason VARCHAR(500) NULL;

ALTER TABLE mapping_sessions
    ADD CONSTRAINT uk_mapping_sessions_stop_command_id UNIQUE (stop_command_id);
