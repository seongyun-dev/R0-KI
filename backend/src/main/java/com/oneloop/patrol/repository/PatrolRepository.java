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

    /**
     * 통계 KPI용: 단지/기간/상태 기준 순찰 건수.
     * analytics overview의 totalPatrols(COMPLETED만) 분모로 사용한다.
     *
     * <p>robotIds 필터는 hasRobotIds=false면 무시한다.
     * (빈 List IN 절 ClassCastException 방지용 boolean 패턴)
     */
    @Query(
            """
            SELECT COUNT(patrol)
            FROM Patrol patrol
            WHERE patrol.robot.apartmentComplex.id = :apartmentComplexId
              AND patrol.status = :status
              AND patrol.startedAt >= :from
              AND patrol.startedAt <= :to
              AND (:hasRobotIds = false OR patrol.robot.id IN :robotIds)
            """)
    long countByApartmentAndStatusAndStartedAtBetween(
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("status") PatrolStatus status,
            @Param("from") LocalDateTime from,
            @Param("to") LocalDateTime to,
            @Param("hasRobotIds") boolean hasRobotIds,
            @Param("robotIds") List<Long> robotIds);
}
