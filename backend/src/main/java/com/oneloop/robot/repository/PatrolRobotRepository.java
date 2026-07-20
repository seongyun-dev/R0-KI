package com.oneloop.robot.repository;

import com.oneloop.robot.domain.PatrolRobot;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PatrolRobotRepository extends JpaRepository<PatrolRobot, Long> {
    Optional<PatrolRobot> findBySerialNumber(String serialNumber);
}
