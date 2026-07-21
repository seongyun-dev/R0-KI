package com.oneloop.patrol.repository;

import com.oneloop.patrol.domain.RoutePosition;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RoutePositionRepository extends JpaRepository<RoutePosition, Long> {
    List<RoutePosition> findAllByPatrolIdOrderByRecordedAt(Long patrolId);
}
