package com.oneloop.patrol.repository;

import com.oneloop.patrol.domain.PatrolCheckpointVisit;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PatrolCheckpointVisitRepository
        extends JpaRepository<PatrolCheckpointVisit, Long> {

    List<PatrolCheckpointVisit> findAllByPatrolIdOrderByVisitSequence(Long patrolId);
}
