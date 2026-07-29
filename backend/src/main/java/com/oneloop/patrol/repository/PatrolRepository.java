package com.oneloop.patrol.repository;

import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PatrolRepository extends JpaRepository<Patrol, Long> {
    Page<Patrol> findAllByRobotIdOrderByStartedAtDesc(Long robotId, Pageable pageable);

    Optional<Patrol> findFirstByRobotIdOrderByStartedAtDesc(Long robotId);

    boolean existsByRobotIdAndStatus(Long robotId, PatrolStatus status);

    Optional<Patrol> findByCommandId(String commandId);

    List<Patrol> findAllByRobotIdAndStartedAtGreaterThanEqual(Long robotId, LocalDateTime since);

    Optional<Patrol> findByIdAndRobotApartmentComplexId(Long id, Long apartmentComplexId);

    @EntityGraph(attributePaths = "robot")
    @Query(
            """
            SELECT patrol
            FROM Patrol patrol
            WHERE patrol.robot.apartmentComplex.id = :apartmentComplexId
              AND (:status IS NULL OR patrol.status = :status)
              AND (:fromAt IS NULL OR patrol.startedAt >= :fromAt)
              AND (:toAt IS NULL OR patrol.startedAt < :toAt)
            """)
    Page<Patrol> findAllByFilter(
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("status") PatrolStatus status,
            @Param("fromAt") LocalDateTime fromAt,
            @Param("toAt") LocalDateTime toAt,
            Pageable pageable);
}
