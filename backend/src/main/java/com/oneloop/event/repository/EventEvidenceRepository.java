package com.oneloop.event.repository;

import com.oneloop.event.domain.EventEvidence;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EventEvidenceRepository extends JpaRepository<EventEvidence, Long> {
    List<EventEvidence> findAllByEventId(Long eventId);
}
