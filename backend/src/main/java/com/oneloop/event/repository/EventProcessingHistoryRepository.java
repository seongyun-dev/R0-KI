package com.oneloop.event.repository;

import com.oneloop.event.domain.EventProcessingHistory;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EventProcessingHistoryRepository
        extends JpaRepository<EventProcessingHistory, Long> {
    List<EventProcessingHistory> findAllByEventIdOrderByChangedAt(Long eventId);
}
