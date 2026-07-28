package com.oneloop.mapping.event;

import com.oneloop.mapping.dto.response.MappingStatusEventResponse;
import com.oneloop.mapping.service.MappingSseService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
@RequiredArgsConstructor
public class MappingStatusChangedEventListener {

    private final MappingSseService mappingSseService;

    /** DB 상태 변경이 커밋된 뒤에만 프론트로 상태 이벤트를 전송한다. */
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(MappingStatusChangedEvent event) {
        mappingSseService.broadcast(
                event.mappingSessionId(),
                MappingStatusEventResponse.of(
                        event.mappingSessionId(), event.status(), event.mapId()));
    }
}
