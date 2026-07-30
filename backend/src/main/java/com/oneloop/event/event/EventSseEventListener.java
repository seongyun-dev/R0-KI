package com.oneloop.event.event;

import com.oneloop.event.service.EventSseService;
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

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handleEmergency(EmergencyEventCreatedEvent event) {
        log.info(
                "[EVENT_SSE] DB 커밋 확인 channel=emergency apartmentComplexId={} eventId={}",
                event.apartmentComplexId(),
                event.response().getEventId());
        eventSseService.broadcastEmergency(event.apartmentComplexId(), event.response());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handleGeneral(GeneralEventsCreatedEvent event) {
        log.info(
                "[EVENT_SSE] DB 커밋 확인 channel=general apartmentComplexId={} patrolId={} createdCount={}",
                event.apartmentComplexId(),
                event.response().getPatrolId(),
                event.response().getCreatedCount());
        eventSseService.broadcastGeneral(event.apartmentComplexId(), event.response());
    }
}
