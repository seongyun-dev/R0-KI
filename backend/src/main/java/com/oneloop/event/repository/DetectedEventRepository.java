package com.oneloop.event.repository;

import com.oneloop.event.domain.DetectedEvent;
import com.oneloop.event.domain.ProcessingStatus;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DetectedEventRepository extends JpaRepository<DetectedEvent, Long> {
    List<DetectedEvent> findAllByProcessingStatusOrderByOccurredAtDesc(ProcessingStatus status);

    List<DetectedEvent> findAllByPatrolIdOrderByOccurredAt(Long patrolId);
}
