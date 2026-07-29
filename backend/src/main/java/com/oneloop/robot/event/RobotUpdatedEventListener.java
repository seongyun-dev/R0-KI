package com.oneloop.robot.event;

import com.oneloop.robot.dto.response.RobotLocationResponse;
import com.oneloop.robot.dto.response.RobotStatusUpdateResponse;
import com.oneloop.robot.service.RobotLocationSseService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
@RequiredArgsConstructor
public class RobotUpdatedEventListener {

    private final RobotLocationSseService robotLocationSseService;

    /** DB에 최신 위치가 반영된 후 1초 주기의 위치 변경을 지도 구독자에게 전달합니다. */
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handleLocation(RobotLocationUpdatedEvent event) {
        robotLocationSseService.broadcastLocation(
                event.apartmentComplexId(), RobotLocationResponse.from(event));
    }

    /** DB에 상태와 배터리가 반영된 후 status 주기의 변경을 하단 목록 구독자에게 전달합니다. */
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handleStatus(RobotStatusUpdatedEvent event) {
        robotLocationSseService.broadcastStatus(
                event.apartmentComplexId(), RobotStatusUpdateResponse.from(event));
    }
}
