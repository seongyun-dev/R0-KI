package com.oneloop.patrol.scheduler;

import com.oneloop.patrol.domain.Patrol;
import com.oneloop.patrol.domain.PatrolStatus;
import com.oneloop.patrol.repository.PatrolRepository;
import com.oneloop.robot.domain.PatrolRobot;
import com.oneloop.robot.domain.RobotStatus;
import com.oneloop.robot.event.RobotStatusUpdatedEvent;
import java.time.LocalDateTime;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class PatrolConnectionWatchdog {

    private static final List<PatrolStatus> ACTIVE_STATUSES =
            List.of(PatrolStatus.IN_PROGRESS, PatrolStatus.STOP_REQUESTED);

    private final PatrolRepository patrolRepository;
    private final ApplicationEventPublisher eventPublisher;

    @Value("${app.patrol.connection-timeout-seconds:15}")
    private long connectionTimeoutSeconds;

    @Scheduled(fixedDelayString = "${app.patrol.watchdog-interval-ms:5000}")
    @Transactional
    public void failDisconnectedPatrols() {
        // 주행 중 heartbeat가 제한 시간을 넘긴 경우 서버가 실제 위치와 정지 여부를 보장할 수 없다.
        // 따라서 새 순찰을 허용하는 IDLE이 아니라 OFFLINE으로 두고 현재 순찰을 FAILED로 닫는다.
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime threshold = now.minusSeconds(connectionTimeoutSeconds);

        for (Patrol patrol : patrolRepository.findAllByStatusIn(ACTIVE_STATUSES)) {
            PatrolRobot robot = patrol.getRobot();
            if (robot.getLastConnectedAt() != null
                    && !robot.getLastConnectedAt().isBefore(threshold)) {
                // 센서·모터 상태가 포함된 status heartbeat가 최근 수신된 경우에만 연결이 살아 있다고 판단한다.
                continue;
            }

            patrol.fail();
            robot.markOffline();
            eventPublisher.publishEvent(
                    new RobotStatusUpdatedEvent(
                            robot.getApartmentComplex().getId(),
                            robot.getId(),
                            RobotStatus.OFFLINE,
                            robot.getBatteryLevel(),
                            now));
            log.warn(
                    "로봇 통신 시간 초과로 순찰을 실패 처리했습니다. patrolId={}, robotId={}",
                    patrol.getId(),
                    robot.getId());
        }
    }
}
