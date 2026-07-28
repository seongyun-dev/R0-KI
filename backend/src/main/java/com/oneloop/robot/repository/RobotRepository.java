package com.oneloop.robot.repository;

import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import java.util.Collection;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RobotRepository extends JpaRepository<PatrolRobot, Long> {
    Optional<PatrolRobot> findBySerialNumber(String serialNumber);

    Optional<PatrolRobot> findByServiceToken(String serviceToken);

    Page<PatrolRobot> findAllByApartmentComplexIdAndStatusNot(
            Long apartmentComplexId, RobotStatus excludedStatus, Pageable pageable);

    Optional<PatrolRobot> findByIdAndApartmentComplexIdAndStatusNot(
            Long id, Long apartmentComplexId, RobotStatus excludedStatus);

    long countByApartmentComplexIdAndStatusNot(Long apartmentComplexId, RobotStatus excludedStatus);

    long countByApartmentComplexIdAndStatusIn(
            Long apartmentComplexId, Collection<RobotStatus> statuses);
}
