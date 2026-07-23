package com.oneloop.patrol.repository;

import com.oneloop.patrol.domain.PatrolAiSummary;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PatrolAiSummaryRepository extends JpaRepository<PatrolAiSummary, Long> {
    Optional<PatrolAiSummary> findByPatrolId(Long patrolId);
}
