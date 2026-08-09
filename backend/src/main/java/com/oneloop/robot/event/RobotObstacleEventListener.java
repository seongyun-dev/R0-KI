package com.oneloop.robot.event;

import com.oneloop.robot.dto.response.RobotObstacleEventResponse;
import com.oneloop.robot.repository.RobotRepository;
import com.oneloop.robot.service.RobotSseService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
@RequiredArgsConstructor
public class RobotObstacleEventListener {

    private final RobotRepository robotRepository;
    private final RobotSseService robotSseService;

    // DB 커밋 후에만 실행
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(RobotObstacleEvent event) {
        robotRepository
                .findById(event.robotId())
                .ifPresent(
                        robot ->
                                robotSseService.broadcast(
                                        robot.getApartmentComplex().getId(),
                                        RobotObstacleEventResponse.from(event)));
    }
}
