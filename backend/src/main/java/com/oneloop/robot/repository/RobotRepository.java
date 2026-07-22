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

    Page<PatrolRobot> findAllByApartmentComplexId(Long apartmentComplexId, Pageable pageable);

    Optional<PatrolRobot> findByIdAndApartmentComplexId(Long id, Long apartmentComplexId);

    long countByApartmentComplexId(Long apartmentComplexId);

    long countByApartmentComplexIdAndStatusIn(
            Long apartmentComplexId, Collection<RobotStatus> statuses);
}
