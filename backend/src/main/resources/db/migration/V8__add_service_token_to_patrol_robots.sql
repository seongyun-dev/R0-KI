ALTER TABLE patrol_robots
    ADD COLUMN service_token VARCHAR(255) NULL UNIQUE AFTER robot_serial_number;
