ALTER TABLE patrols
    ADD COLUMN command_id VARCHAR(36) NULL AFTER robot_id;

ALTER TABLE patrols
    ADD CONSTRAINT uk_patrols_command_id UNIQUE (command_id);
