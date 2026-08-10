package com.oneloop.robot.repository;

import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import jakarta.persistence.LockModeType;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface RobotRepository extends JpaRepository<PatrolRobot, Long> {
    Optional<PatrolRobot> findBySerialNumber(String serialNumber);

    Optional<PatrolRobot> findByServiceToken(String serviceToken);

    Optional<PatrolRobot> findByIdAndStatusNot(Long id, RobotStatus excludedStatus);

    Page<PatrolRobot> findAllByApartmentComplexIdAndStatusNot(
            Long apartmentComplexId, RobotStatus excludedStatus, Pageable pageable);

    List<PatrolRobot> findAllByApartmentComplexIdAndStatusInOrderByIdAsc(
            Long apartmentComplexId, Collection<RobotStatus> statuses);

    Optional<PatrolRobot> findByIdAndApartmentComplexIdAndStatusNot(
            Long id, Long apartmentComplexId, RobotStatus excludedStatus);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query(
            """
            SELECT robot
            FROM PatrolRobot robot
            WHERE robot.id = :robotId
              AND robot.apartmentComplex.id = :apartmentComplexId
              AND robot.status <> :excludedStatus
            """)
    Optional<PatrolRobot> findForUpdateByIdAndApartmentComplexIdAndStatusNot(
            @Param("robotId") Long robotId,
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("excludedStatus") RobotStatus excludedStatus);

    long countByApartmentComplexIdAndStatusNot(Long apartmentComplexId, RobotStatus excludedStatus);

    long countByApartmentComplexIdAndStatusIn(
            Long apartmentComplexId, Collection<RobotStatus> statuses);
}
