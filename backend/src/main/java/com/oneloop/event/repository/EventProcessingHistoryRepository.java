package com.oneloop.event.repository;

import com.oneloop.event.domain.EventProcessingHistory;
import com.oneloop.event.domain.ProcessingStatus;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EventProcessingHistoryRepository
        extends JpaRepository<EventProcessingHistory, Long> {
    // 목록 페이지 담당자 배치 조회용 - 이벤트별 최신 처리이력을 한 번에 가져와 N+1 방지
    List<EventProcessingHistory> findAllByEventIdInOrderByChangedAtDesc(List<Long> eventIds);

    // 상세 페이지 처리메모용 - 해당 이벤트가 COMPLETED로 바뀐 시점의 처리이력 1건
    Optional<EventProcessingHistory> findFirstByEventIdAndChangedStatusOrderByChangedAtDesc(
            Long eventId, ProcessingStatus changedStatus);
}
