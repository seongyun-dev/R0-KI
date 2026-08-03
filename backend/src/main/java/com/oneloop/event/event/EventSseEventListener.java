package com.oneloop.event.event;

import com.oneloop.event.dto.response.PatrolCompletedSseResponse;
import com.oneloop.event.service.EventSseService;
import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.event.PatrolCompletedEvent;
import com.oneloop.patrol.repository.PatrolRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
@RequiredArgsConstructor
@Slf4j
public class EventSseEventListener {

    private final EventSseService eventSseService;
    private final PatrolRepository patrolRepository;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handleEmergency(EmergencyEventCreatedEvent event) {
        log.info(
                "[EVENT_SSE] DB 커밋 확인 channel=emergency apartmentComplexId={} eventId={}",
                event.apartmentComplexId(),
                event.response().getEventId());
        eventSseService.broadcastEmergency(event.apartmentComplexId(), event.response());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handlePatrolCompleted(PatrolCompletedEvent event) {
        Patrol patrol = patrolRepository.findById(event.patrolId()).orElse(null);
        if (patrol == null) {
            log.warn("[EVENT_SSE] 순찰 완료 SSE 발송 실패: patrolId={}를 찾을 수 없습니다.", event.patrolId());
            return;
        }
        Long apartmentComplexId = patrol.getRobot().getApartmentComplex().getId();
        log.info(
                "[EVENT_SSE] DB 커밋 확인 channel=general patrolId={} apartmentComplexId={}",
                event.patrolId(),
                apartmentComplexId);
        eventSseService.broadcastPatrolCompleted(
                apartmentComplexId, PatrolCompletedSseResponse.from(patrol));
    }
}
