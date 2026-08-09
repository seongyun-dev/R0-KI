ALTER TABLE patrol_robots
    ADD COLUMN obstacle_direction VARCHAR(20) NULL AFTER robot_status;

ALTER TABLE patrol_robots
    ADD COLUMN obstacle_message VARCHAR(255) NULL AFTER obstacle_direction;
