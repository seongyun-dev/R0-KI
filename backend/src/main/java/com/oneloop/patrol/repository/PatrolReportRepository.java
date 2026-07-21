package com.oneloop.patrol.repository;

import com.oneloop.patrol.domain.PatrolReport;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PatrolReportRepository extends JpaRepository<PatrolReport, Long> {
    Optional<PatrolReport> findByPatrolId(Long patrolId);
}
