package com.oneloop.patrol.repository;

import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PatrolCheckpointVisitRepository
        extends JpaRepository<PatrolCheckpointVisit, Long> {

    List<PatrolCheckpointVisit> findAllByPatrolIdOrderByVisitSequence(Long patrolId);

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
}
