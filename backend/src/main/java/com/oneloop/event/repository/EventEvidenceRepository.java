package com.oneloop.event.repository;

import com.oneloop.event.domain.EventEvidence;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EventEvidenceRepository extends JpaRepository<EventEvidence, Long> {
    // 이벤트당 증거자료 1건 - 상세조회 응답에 단일 증거자료로 노출
    Optional<EventEvidence> findFirstByEventIdOrderByCapturedAtDesc(Long eventId);
}
