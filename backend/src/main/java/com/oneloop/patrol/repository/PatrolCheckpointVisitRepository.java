package com.oneloop.patrol.repository;

import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PatrolCheckpointVisitRepository
        extends JpaRepository<PatrolCheckpointVisit, Long> {

    List<PatrolCheckpointVisit> findAllByPatrolIdOrderByVisitSequence(Long patrolId);

    Optional<PatrolCheckpointVisit> findFirstByPatrolIdOrderByVisitSequenceDesc(Long patrolId);

    /**
     * 방문 + 체크포인트를 한 번에 가져온다.
     *
     * <p>트랜잭션 밖(PDF 생성 등)에서 checkpoint 를 읽어야 할 때는 반드시 이 메서드를 쓴다. 위의 파생 메서드는 checkpoint 가 LAZY 라
     * 세션이 닫힌 뒤 좌표를 읽는 순간 LazyInitializationException 이 난다 (open-in-view 가 꺼져 있다).
     */
    @Query(
            """
            SELECT visit
            FROM PatrolCheckpointVisit visit
            JOIN FETCH visit.checkpoint
            WHERE visit.patrol.id = :patrolId
            ORDER BY visit.visitSequence
            """)
    List<PatrolCheckpointVisit> findAllWithCheckpointByPatrolId(@Param("patrolId") Long patrolId);

    @Query(
            """
            SELECT visit
            FROM PatrolCheckpointVisit visit
            JOIN FETCH visit.patrol
            JOIN FETCH visit.checkpoint
            WHERE visit.patrol.id IN :patrolIds
            ORDER BY visit.patrol.id, visit.visitSequence
            """)
    List<PatrolCheckpointVisit> findAllByPatrolIds(
            @Param("patrolIds") List<Long> patrolIds);

    /**
     * 단지/기간 기준 체크포인트(구역)별 방문 횟수를 집계한다.
     * analytics by-zone API의 patrolCount(분모)로 사용한다.
     *
     * <p>반환: Object[0]=checkpointId(Long), Object[1]=visitCount(Long)
     */
    @Query(
            """
            SELECT visit.checkpoint.id, COUNT(visit)
            FROM PatrolCheckpointVisit visit
            WHERE visit.patrol.robot.apartmentComplex.id = :apartmentComplexId
              AND visit.visitedAt >= :from
              AND visit.visitedAt <= :to
              AND (:hasRobotIds = false OR visit.patrol.robot.id IN :robotIds)
            GROUP BY visit.checkpoint.id
            """)
    List<Object[]> countVisitsGroupedByCheckpoint(
            @Param("apartmentComplexId") Long apartmentComplexId,
            @Param("from") LocalDateTime from,
            @Param("to") LocalDateTime to,
            @Param("hasRobotIds") boolean hasRobotIds,
            @Param("robotIds") List<Long> robotIds);

    @Modifying(flushAutomatically = true)
    @Query(
            """
            DELETE FROM PatrolCheckpointVisit visit
            WHERE visit.checkpoint.patrolMap.id = :mapId
            """)
    int deleteAllByCheckpointPatrolMapId(@Param("mapId") Long mapId);
}
